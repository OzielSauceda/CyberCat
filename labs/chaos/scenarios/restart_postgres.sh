#!/usr/bin/env bash
# labs/chaos/scenarios/restart_postgres.sh
#
# Phase 19.5 scenario A2: restart Postgres mid-load. Verifies that
# `with_ingest_retry()` (backend/app/ingest/retry.py) and the explicit pool
# config (pool_size=20, max_overflow=10, pool_recycle=1800, pool_timeout=10,
# pool_pre_ping=True) keep the ingest path alive when Postgres bounces.
#
# Test recipe:
#   1. Wipe demo data so the events count is clean.
#   2. Run load_harness.py at 100/s × 30s (inside backend container so we
#      don't depend on host httpx).
#   3. At t=10s: `docker compose restart postgres`.
#   4. Wait for harness to finish.
#   5. Evaluate four §A1 acceptance counters + one A2-specific check
#      (no orphan rows in incident_events).
#
# Pass criteria:
#   - sim_tracebacks       == 0
#   - backend_tracebacks   == 0
#   - event_count_5min     > 0      (events landed during/after restart)
#   - degraded_warnings    > 0      (with_ingest_retry actually fired)
#   - orphan_incidents     == 0     (no incident rows without incident_events)
#   - harness acceptance_passed == true (≥95% accept, no transport_errors)
#
# Usage (after `bash start.sh`):
#   bash labs/chaos/scenarios/restart_postgres.sh
#
# Override defaults via env vars:
#   RATE=200 DURATION=60 RESTART_AT=20 bash labs/chaos/scenarios/restart_postgres.sh
#
# CI equivalent: .github/workflows/chaos-postgres.yml

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults (overridable via env)
# ----------------------------------------------------------------------------
: "${RATE:=100}"            # events/sec
: "${DURATION:=30}"          # seconds
: "${RESTART_AT:=10}"        # seconds into the run when postgres gets bounced
: "${SCENARIO_NAME:=restart_postgres}"

# Defensive trap: ensure stack returns to usable state even on script failure.
trap 'cleanup_chaos_state' EXIT

echo "================================================================"
echo "  chaos scenario A2: restart_postgres"
echo "  rate=$RATE/s  duration=${DURATION}s  restart_at=${RESTART_AT}s"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pre-flight: stack must be up; wipe demo data for a clean event count.
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable at http://localhost:8000/healthz — bring up the stack with 'bash start.sh' first"
    exit 1
fi

# Demo-data wipe needs admin role. The cct-agent token is `analyst`, so this
# would 403. Skip the wipe and rely on the 5-min event window below — the
# baseline auto-seed events fall outside the chaos window we measure.
echo "[$(date +%T)] Pre-flight OK. (Skipping demo-data wipe — admin-only endpoint, analyst token cannot use it.)"

# ----------------------------------------------------------------------------
# Start the load harness in the background, inside the backend container so
# we don't depend on host httpx.
# ----------------------------------------------------------------------------
HARNESS_LOG="/tmp/cct_chaos_a2_harness.log"
: > "$HARNESS_LOG"

echo "[$(date +%T)] Starting load harness ${RATE}/s × ${DURATION}s inside backend container..."
MSYS_NO_PATHCONV=1 docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T backend python labs/perf/load_harness.py \
    --base-url http://localhost:8000 --rate "$RATE" --duration "$DURATION" \
    > "$HARNESS_LOG" 2>&1 &
HARNESS_PID=$!
: "${HARNESS_PID:=0}"
echo "[$(date +%T)] Harness PID=$HARNESS_PID. Sleeping ${RESTART_AT}s before postgres restart..."

sleep "$RESTART_AT"

# ----------------------------------------------------------------------------
# The chaos: restart postgres mid-flight.
# ----------------------------------------------------------------------------
echo "----- restart postgres -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    restart postgres
echo "[$(date +%T)] Postgres restart issued. Waiting for harness to finish..."

# Wait for harness completion. `wait` returns the harness exit code.
if [ "$HARNESS_PID" -gt 0 ]; then
    wait "$HARNESS_PID" || true
    HARNESS_EXIT=$?
else
    HARNESS_EXIT=99
fi

echo "[$(date +%T)] Harness done. exit=$HARNESS_EXIT (informational; the four §A1 counters are the pass criteria)"

# ----------------------------------------------------------------------------
# Capture logs inline. The load_harness output IS the sim.log for this scenario.
# ----------------------------------------------------------------------------
echo "================================================================"
echo "  load_harness output (sim.log equivalent)"
echo "================================================================"
cat "$HARNESS_LOG" || true
echo "================================================================"
echo "  end harness output"
echo "================================================================"

BACKEND_LOG="/tmp/cct_chaos_a2_backend.log"
capture_backend_log "$BACKEND_LOG" 250
echo "================================================================"
echo "  backend logs (last 250 lines)"
echo "================================================================"
cat "$BACKEND_LOG" || true
echo "================================================================"
echo "  end backend logs"
echo "================================================================"

# ----------------------------------------------------------------------------
# Compute the four §A1 counters using shared helpers, plus A2-specific checks.
# ----------------------------------------------------------------------------
SIM_TB=$(count_traceback_lines "$HARNESS_LOG")
BE_TB=$(count_traceback_lines "$BACKEND_LOG")
EVT_COUNT=$(count_postgres_events_5min)

# A2-specific degraded pattern: with_ingest_retry / connection_invalidated
# (the SQLAlchemy DBAPIError message that triggers the retry decorator) plus
# the generic "Lost connection to MySQL/Postgres" / "could not connect to
# server" patterns from a postgres bounce. Phase 19's retry.py logs a single
# warning-level line when the retry triggers.
DEGRADED=$(count_degraded_warnings "$BACKEND_LOG" \
    "with_ingest_retry|connection_invalidated|could not connect to server|server closed the connection unexpectedly|InterfaceError|OperationalError")

# A2-specific orphan-rows check: incidents without any matching incident_events
# would mean a half-written incident from a bounce that wasn't transactionally
# clean. Should always be 0.
ORPHAN_INCIDENTS=$(docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -t -A \
    -c "SELECT count(*) FROM incidents WHERE id NOT IN (SELECT incident_id FROM incident_events);" \
    2>/dev/null \
    | tr -d ' \r\n')
: "${ORPHAN_INCIDENTS:=0}"

# Pull harness acceptance verdict from the JSON summary. The harness emits a
# single JSON object on stdout with `acceptance_passed: bool`.
HARNESS_ACCEPTANCE=$(grep -E '"acceptance_passed":' "$HARNESS_LOG" \
    | head -1 \
    | grep -oE '(true|false)' \
    | head -1 \
    || echo "unknown")
: "${HARNESS_ACCEPTANCE:=unknown}"

print_acceptance_summary "$SIM_TB" "$BE_TB" "$EVT_COUNT" "$DEGRADED"
echo "  A2 extras:"
printf "    orphan_incidents   = %s  (must be 0)\n" "$ORPHAN_INCIDENTS"
printf "    harness_accept     = %s  (must be true)\n" "$HARNESS_ACCEPTANCE"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision.
# ----------------------------------------------------------------------------
FAIL=0
if [ "$SIM_TB" -gt 0 ]; then
    echo "FAIL: load_harness produced $SIM_TB traceback(s) — should degrade gracefully through postgres restart"
    FAIL=1
fi
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend produced $BE_TB traceback(s) — with_ingest_retry should catch DBAPI invalidation cleanly"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in postgres last 5 min — ingest didn't survive the restart"
    FAIL=1
fi
if [ "$DEGRADED" -le 0 ]; then
    echo "FAIL: 0 degraded-mode warnings in backend log — the retry layer didn't fire (or chaos missed the right code path; tune RESTART_AT)"
    FAIL=1
fi
if [ "$ORPHAN_INCIDENTS" -gt 0 ]; then
    echo "FAIL: $ORPHAN_INCIDENTS orphan incident(s) without incident_events — half-written incident from the bounce"
    FAIL=1
fi
if [ "$HARNESS_ACCEPTANCE" != "true" ]; then
    echo "FAIL: load_harness acceptance failed (acceptance_passed=$HARNESS_ACCEPTANCE) — see harness output above for violations"
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A2 acceptance NOT met — see counters above"
    exit 1
fi

echo "PASS: §A2 acceptance met — postgres bounce did not break ingest"
exit 0
