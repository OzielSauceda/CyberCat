#!/usr/bin/env bash
# labs/chaos/scenarios/kill_redis.sh
#
# Phase 19.5 scenario A1: kill Redis mid-load. Verifies that `safe_redis()`
# (backend/app/db/redis_state.py) and `EventBus._supervisor()`
# (backend/app/streaming/bus.py:97-123) keep the ingest path alive when
# Redis dies abruptly and stays dead for ~15s before being restored.
#
# Test recipe:
#   1. Pre-flight: backend reachable.
#   2. Run load_harness.py at 100/s × 30s (inside backend container so we
#      don't depend on host httpx — matches A2/A6 pattern).
#   3. At t=10s: `docker compose kill redis` (SIGKILL — abrupt, no SIGTERM
#      grace window; that's the worst case we're testing).
#   4. At t=25s: `docker compose up -d redis` (restore).
#   5. Wait for harness to finish at t=30s.
#   6. Evaluate four §A1 acceptance counters.
#
# Pass criteria (matches docs/phase-19-plan.md line 67 + chaos-redis.yml
# inline eval — this script is the local single-source-of-truth that the
# CI workflow optionally sources via lib/evaluate.sh):
#   - sim_tracebacks       == 0    (load_harness degraded gracefully)
#   - backend_tracebacks   == 0    (safe_redis swallowed every redis call)
#   - event_count_5min     > 0     (ingest survived; events landed)
#   - degraded_warnings    > 0     (redis_degraded log fired — proves
#                                   safe_redis actually engaged, not lucky
#                                   timing on the kill window)
#
# accept_pct and transport_errors are PRINTED but NOT gated. The §A1 plan
# (docs/phase-19.5-plan.md line 30) defines pass as the four counters
# above — accept_pct/transport_errors were over-spec'd from restart_postgres.sh
# during initial drafting. On Windows+WSL2 specifically, accept_pct
# *will* drop and transport_errors *will* spike during the dead-redis
# window because `getaddrinfo("redis")` takes ~3.6s to return NXDOMAIN
# on WSL2 (vs near-instant on real Linux). This is a documented platform
# quirk, not a backend regression — see chaos-redis.yml header. The CI
# workflow runs on ubuntu-latest where the quirk doesn't apply.
#
# Usage (after `bash start.sh`):
#   bash labs/chaos/scenarios/kill_redis.sh
#
# Override defaults via env vars:
#   RATE=200 DURATION=60 KILL_AT=20 RESTORE_AFTER=20 \
#       bash labs/chaos/scenarios/kill_redis.sh
#
# CI equivalent: .github/workflows/chaos-redis.yml (uses the simulator with
# --no-verify rather than load_harness; both drivers exercise the same
# safe_redis code path, but the local script uses load_harness for
# deterministic counters).

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults (overridable via env)
# ----------------------------------------------------------------------------
: "${RATE:=100}"            # events/sec
: "${DURATION:=30}"          # seconds
: "${KILL_AT:=10}"           # seconds into the run when redis gets killed
: "${RESTORE_AFTER:=15}"     # seconds redis stays dead before restore
: "${SCENARIO_NAME:=kill_redis}"
# transport_errors is NOT gated (see header comment). The default is
# kept here as informational only — printed in the summary block but
# not used in the pass/fail decision.
: "${TRANSPORT_ERRORS_MAX:=99999}"

# Defensive trap: ensure stack returns to usable state even on script
# failure. cleanup_chaos_state in lib/evaluate.sh already restarts redis
# if it's missing, so a Ctrl-C during the dead-redis window leaves us in
# a usable state.
trap 'cleanup_chaos_state' EXIT

echo "================================================================"
echo "  chaos scenario A1: kill_redis"
echo "  rate=$RATE/s  duration=${DURATION}s  kill_at=${KILL_AT}s  restore_after=${RESTORE_AFTER}s"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pre-flight: stack must be up.
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable at http://localhost:8000/healthz — bring up the stack with 'bash start.sh' first"
    exit 1
fi

# Demo-data wipe needs admin role. The cct-agent token is `analyst`, so this
# would 403. Skip the wipe and rely on the 5-min event window — the baseline
# auto-seed events fall outside the chaos window we measure.
echo "[$(date +%T)] Pre-flight OK. (Skipping demo-data wipe — admin-only endpoint, analyst token cannot use it.)"

# ----------------------------------------------------------------------------
# Start the load harness in the background, inside the backend container so
# we don't depend on host httpx.
# ----------------------------------------------------------------------------
HARNESS_LOG="/tmp/cct_chaos_a1_harness.log"
: > "$HARNESS_LOG"

echo "[$(date +%T)] Starting load harness ${RATE}/s × ${DURATION}s inside backend container..."
MSYS_NO_PATHCONV=1 docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T backend python labs/perf/load_harness.py \
    --base-url http://localhost:8000 --rate "$RATE" --duration "$DURATION" \
    > "$HARNESS_LOG" 2>&1 &
HARNESS_PID=$!
: "${HARNESS_PID:=0}"
echo "[$(date +%T)] Harness PID=$HARNESS_PID. Sleeping ${KILL_AT}s before redis kill..."

sleep "$KILL_AT"

# ----------------------------------------------------------------------------
# The chaos: kill redis (SIGKILL) — most aggressive form. No SIGTERM grace
# period. From safe_redis's perspective the connection just disappears
# mid-call.
# ----------------------------------------------------------------------------
echo "----- kill redis -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    kill redis || true
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" ps || true
echo "[$(date +%T)] Redis killed. Holding dead for ${RESTORE_AFTER}s..."

sleep "$RESTORE_AFTER"

echo "----- restore redis -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    up -d redis || true
echo "[$(date +%T)] Redis restored. Waiting for harness to finish..."

# Wait for harness completion. `wait` returns the harness exit code; we
# treat it as informational because the four §A1 counters below are the
# pass criteria.
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

BACKEND_LOG="/tmp/cct_chaos_a1_backend.log"
# Capture by time window, not tail line count. The 250-line tail used by
# A2-A6 is too short for A1: the load_harness ingest path logs ~20
# sqlalchemy.engine.Engine INFO lines per event (roughly 60 events/sec
# × 30s = 36k SQL lines for a full run), which buries the relatively
# sparse "redis_degraded" / "EventBus consumer crashed" lines that
# we're counting on. Use --since to grab the entire chaos window.
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    logs backend --since 2m \
    > "$BACKEND_LOG" 2>&1 || true
echo "================================================================"
echo "  backend logs (last 2 minutes, redis-related lines only)"
echo "================================================================"
# Print the resilience-relevant lines inline so the chaos signal is
# visible in the script output. Full log stays on disk in $BACKEND_LOG.
grep -iE "redis|degraded|safe_redis|EventBus|ConnectionError" "$BACKEND_LOG" | head -50 || true
echo "================================================================"
echo "  end backend logs (full $(wc -l < "$BACKEND_LOG" 2>/dev/null || echo 0) lines on disk at $BACKEND_LOG)"
echo "================================================================"

# ----------------------------------------------------------------------------
# Compute the four §A1 counters using shared helpers.
# ----------------------------------------------------------------------------
SIM_TB=$(count_traceback_lines "$HARNESS_LOG")
BE_TB=$(count_traceback_lines "$BACKEND_LOG")
EVT_COUNT=$(count_postgres_events_5min)

# A1 degraded pattern — matches docs/phase-19.5-plan.md line 30:
# "redis_degraded|redis_state=unavailable|degraded mode|EventBus consumer crashed"
# These are the four distinct log shapes safe_redis() and the EventBus
# supervisor emit when redis is unreachable. Any one of them firing
# proves the resilience layer engaged.
DEGRADED=$(count_degraded_warnings "$BACKEND_LOG" \
    "redis_degraded|redis_state=unavailable|degraded mode|EventBus consumer crashed")

# Pull harness raw counters from the JSON summary line.
HARNESS_SENT=$(grep -E '"sent":' "$HARNESS_LOG" | head -1 \
    | grep -oE '[0-9]+' | head -1 || echo 0)
: "${HARNESS_SENT:=0}"
HARNESS_ACCEPTED=$(grep -E '"accepted":' "$HARNESS_LOG" | head -1 \
    | grep -oE '[0-9]+' | head -1 || echo 0)
: "${HARNESS_ACCEPTED:=0}"
HARNESS_FAILED_5XX=$(grep -E '"failed_5xx":' "$HARNESS_LOG" | head -1 \
    | grep -oE '[0-9]+' | head -1 || echo 0)
: "${HARNESS_FAILED_5XX:=0}"
HARNESS_TRANSPORT_ERRORS=$(grep -E '"transport_errors":' "$HARNESS_LOG" | head -1 \
    | grep -oE '[0-9]+' | head -1 || echo 0)
: "${HARNESS_TRANSPORT_ERRORS:=0}"
HARNESS_P95=$(grep -E '"p95":' "$HARNESS_LOG" | head -1 \
    | grep -oE '[0-9]+(\.[0-9]+)?' | head -1 || echo 0)
: "${HARNESS_P95:=0}"

# Acceptance ratio (integer percentage).
if [ "$HARNESS_SENT" -gt 0 ]; then
    ACCEPT_PCT=$(( (HARNESS_ACCEPTED * 100) / HARNESS_SENT ))
else
    ACCEPT_PCT=0
fi

print_acceptance_summary "$SIM_TB" "$BE_TB" "$EVT_COUNT" "$DEGRADED"
echo "  A1 extras (load_harness counters — informational, NOT gated on WSL2):"
printf "    sent / accepted    = %s / %s  (accept_pct=%s%%)\n" "$HARNESS_SENT" "$HARNESS_ACCEPTED" "$ACCEPT_PCT"
printf "    failed_5xx         = %s  (informational; redis-down may produce some)\n" "$HARNESS_FAILED_5XX"
printf "    transport_errors   = %s  (informational; WSL2 DNS quirk — see header)\n" "$HARNESS_TRANSPORT_ERRORS"
printf "    latency p95        = %sms  (informational)\n" "$HARNESS_P95"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision — strict §A1 criteria.
#
# Note on degraded_warnings: unlike A4 (where degraded_warnings was relaxed
# to informational because the cursor-advance assertion was the real proof),
# A1 KEEPS degraded_warnings > 0 as a hard requirement. The redis_degraded
# log line is the smoking gun that safe_redis actually engaged — without it,
# we got lucky timing (the kill missed every redis call) and the test isn't
# proving anything.
# ----------------------------------------------------------------------------
FAIL=0
if [ "$SIM_TB" -gt 0 ]; then
    echo "FAIL: load_harness produced $SIM_TB traceback(s) — should degrade gracefully through redis kill"
    FAIL=1
fi
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend produced $BE_TB traceback(s) — safe_redis should swallow every redis call cleanly"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in postgres last 5 min — ingest didn't survive the redis kill"
    FAIL=1
fi
if [ "$DEGRADED" -le 0 ]; then
    echo "FAIL: degraded_warnings=0 — safe_redis didn't fire (or the kill window missed every redis call). Tune KILL_AT/RESTORE_AFTER or check that the safe_redis log emit is wired."
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A1 acceptance NOT met — see counters above"
    exit 1
fi

echo "PASS: §A1 acceptance met — ${DEGRADED} degraded warning(s), ${EVT_COUNT} events in last 5min, 0 tracebacks (accept_pct=${ACCEPT_PCT}% informational on WSL2)"
exit 0
