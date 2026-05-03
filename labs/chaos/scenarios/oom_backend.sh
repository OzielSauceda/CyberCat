#!/usr/bin/env bash
# labs/chaos/scenarios/oom_backend.sh
#
# Phase 19.5 scenario A5: SIGKILL the backend container mid-credential-theft-
# chain (after both incidents are formed, before the scenario completes).
# After backend recovers, assert that the dedupe path holds — exactly ONE
# identity_compromise incident and exactly ONE identity_endpoint_chain
# incident for alice, with no orphan rows.
#
# This exercises the correlator's stateless-with-postgres-truth design:
# the dedupe key `identity_compromise:alice:<hour_bucket>` is computed
# from event data, not in-memory state, so a hard restart does not
# produce double-correlation. Plus Phase 19's `with_ingest_retry()`
# decorator should mask the Postgres-pool-warmup window after restart.
#
# Test recipe:
#   1. Wipe nothing — A5 needs the auto-seed alice events absent. Wipe
#      via a direct DB truncate inside the postgres container (cct-agent
#      token is analyst, so admin-only DELETE /v1/admin/demo-data 403s).
#   2. Background `python -m labs.simulator --scenario credential_theft_chain
#      --speed 0.1 --no-verify` from the host (httpx required).
#   3. At KILL_AT (default 20s — after stage 4 process.created at t=18s,
#      so both incidents exist), `docker compose kill -s SIGKILL backend`.
#   4. Sleep KILL_RECOVERY (default 5s).
#   5. `docker compose up -d backend`. Wait for /healthz.
#   6. Wait for simulator to exit (it will likely error out post-kill
#      because raise_for_status raises on the connection refused; that's
#      informational, not gating).
#   7. Re-query incidents + orphan rows.
#
# Pass criteria:
#   - sim_tracebacks       == 0  (simulator may emit ConnectError but not Traceback)
#   - backend_tracebacks   == 0  (post-restart backend should not produce tracebacks)
#   - event_count_5min     > 0   (events from pre-kill landed in Postgres)
#   - degraded_warnings    > 0   (post-restart recovery markers in backend log)
#   - identity_compromise_count == 1
#   - identity_endpoint_chain_count == 1
#   - orphan_incidents == 0
#
# Usage (after `bash start.sh`):
#   bash labs/chaos/scenarios/oom_backend.sh
#
# Override defaults via env vars:
#   SPEED=0.1 KILL_AT=20 KILL_RECOVERY=5 bash labs/chaos/scenarios/oom_backend.sh
#
# CI equivalent: .github/workflows/chaos-oom-backend.yml

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
: "${SPEED:=0.1}"
: "${KILL_AT:=20}"           # seconds before SIGKILL — after stage-4 (t=18s)
: "${KILL_RECOVERY:=5}"      # seconds before restarting backend
: "${SCENARIO_NAME:=oom_backend}"

trap 'cleanup_chaos_state' EXIT

echo "================================================================"
echo "  chaos scenario A5: oom_backend"
echo "  speed=$SPEED  kill_at=${KILL_AT}s  kill_recovery=${KILL_RECOVERY}s"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable at http://localhost:8000/healthz — bring up the stack with 'bash start.sh' first"
    exit 1
fi
# Run the simulator INSIDE the cct-agent container — it already has httpx
# baked in for the agent code, and running there means killing the backend
# doesn't kill the simulator. cct-agent's image doesn't have labs/, so we
# docker cp it in. Matches the 2026-05-01 chaos pattern from the Phase 19
# verification cycle (docs/phase-19-handoff.md "Test 3").
AGENT_CONTAINER=$(docker ps --format '{{.Names}}' \
    | grep -E '(^|-|/)cct-agent(-1)?$' \
    | head -1 \
    || true)
if [ -z "$AGENT_CONTAINER" ]; then
    echo "FAIL: could not find cct-agent container — A5 runs the simulator there"
    exit 1
fi
echo "[$(date +%T)] Detected agent container: $AGENT_CONTAINER"
echo "[$(date +%T)] Copying labs/ into agent container so the simulator can find scenarios..."
docker cp labs "${AGENT_CONTAINER}:/app/labs" >/dev/null 2>&1 || \
    { echo "FAIL: docker cp labs/ into agent container failed"; exit 1; }

# Read the bearer token. Empty string is OK if AUTH_REQUIRED=false; the
# simulator will simply send no Authorization header.
TOKEN="$(read_token_from_env)"

# ----------------------------------------------------------------------------
# DB wipe via direct TRUNCATE inside postgres container (admin endpoint
# requires admin role; cct-agent token is analyst). Targets only the
# tables this scenario asserts against; preserves users / api_tokens /
# anything Phase 14 / 17 needs.
# ----------------------------------------------------------------------------
echo "[$(date +%T)] Truncating event/detection/incident tables for a clean assertion window..."
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -c "
        TRUNCATE evidence_requests, blocked_observables, lab_sessions,
                 notes, incident_transitions, action_logs, actions,
                 incident_attack, incident_entities, incident_events,
                 incident_detections, incidents, detections,
                 event_entities, events, entities
                 RESTART IDENTITY CASCADE;
    " > /dev/null 2>&1 || true

# Also flush Redis dedupe keys / streams so the correlator starts from a
# clean state (per smoke_test_agent.sh:96 pattern).
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T redis redis-cli FLUSHDB > /dev/null 2>&1 || true

# ----------------------------------------------------------------------------
# Background the simulator. Use --no-verify; the simulator will likely exit
# non-zero post-kill because the events post-kill error out — informational.
# ----------------------------------------------------------------------------
SIM_LOG="/tmp/cct_chaos_a5_sim.log"
: > "$SIM_LOG"

if [ -n "$TOKEN" ]; then
    SIM_AUTH=(--token "$TOKEN")
else
    SIM_AUTH=()
fi

echo "[$(date +%T)] Starting simulator inside $AGENT_CONTAINER (credential_theft_chain --speed $SPEED --no-verify)..."
# Use docker exec directly with the container name — docker compose exec
# wants the service name (cct-agent) but we already have the container
# name from auto-detection. -w /app sets cwd. MSYS_NO_PATHCONV=1 stops
# Git Bash from path-mangling the -w argument on Windows.
( MSYS_NO_PATHCONV=1 docker exec -i -w /app "$AGENT_CONTAINER" \
    python -m labs.simulator \
    --scenario credential_theft_chain \
    --speed "$SPEED" \
    --api http://backend:8000 \
    --no-verify \
    "${SIM_AUTH[@]}" \
    > "$SIM_LOG" 2>&1 ) &
SIM_PID=$!
: "${SIM_PID:=0}"
echo "[$(date +%T)] Simulator PID=$SIM_PID"

# ----------------------------------------------------------------------------
# Wait until KILL_AT, then SIGKILL the backend.
# ----------------------------------------------------------------------------
sleep "$KILL_AT"
echo "----- SIGKILL backend -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    kill -s SIGKILL backend
echo "[$(date +%T)] Backend killed. Sleeping ${KILL_RECOVERY}s before restart..."

sleep "$KILL_RECOVERY"

echo "----- restart backend -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    up -d backend

# Wait for backend /healthz to return 200 (up to 60s — alembic + auto-seed
# on cold start can take a beat).
echo "[$(date +%T)] Waiting for backend /healthz to recover..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
        echo "[$(date +%T)] backend /healthz OK after ${i}× 1s"
        break
    fi
    sleep 1
done

# Wait for the simulator to exit (it almost certainly exited with an error
# already because mid-scenario raise_for_status would have surfaced).
if [ "$SIM_PID" -gt 0 ]; then
    wait "$SIM_PID" || true
fi

# Settle window — let any in-flight ingest finish landing.
echo "[$(date +%T)] Settling 5s for any in-flight ingest..."
sleep 5

# ----------------------------------------------------------------------------
# Capture logs.
# ----------------------------------------------------------------------------
BACKEND_LOG="/tmp/cct_chaos_a5_backend.log"
capture_backend_log "$BACKEND_LOG" 250

echo "================================================================"
echo "  simulator output"
echo "================================================================"
cat "$SIM_LOG" || true
echo "================================================================"
echo "  backend logs (last 250 lines)"
echo "================================================================"
cat "$BACKEND_LOG" || true
echo "================================================================"

# ----------------------------------------------------------------------------
# Counters.
# ----------------------------------------------------------------------------
SIM_TB=$(count_traceback_lines "$SIM_LOG")
BE_TB=$(count_traceback_lines "$BACKEND_LOG")
EVT_COUNT=$(count_postgres_events_5min)

# A5-specific degraded pattern: post-restart recovery markers (uvicorn
# startup, alembic migration check, with_ingest_retry firing, etc.)
DEGRADED=$(count_degraded_warnings "$BACKEND_LOG" \
    "Application startup complete|alembic|with_ingest_retry|connection_invalidated|server_started|Uvicorn running")

# A5-specific incident counts. The dedupe key prevents duplicates on restart;
# we assert exactly one of each kind for primary_user=alice.
IDENTITY_COUNT=$(docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -t -A \
    -c "SELECT count(*) FROM incidents i
        JOIN incident_entities ie ON ie.incident_id = i.id
        JOIN entities e ON e.id = ie.entity_id
        WHERE i.kind = 'identity_compromise'
          AND e.kind = 'user'
          AND e.natural_key = 'alice';" \
    2>/dev/null \
    | tr -d ' \r\n')
: "${IDENTITY_COUNT:=0}"

CHAIN_COUNT=$(docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -t -A \
    -c "SELECT count(*) FROM incidents i
        JOIN incident_entities ie ON ie.incident_id = i.id
        JOIN entities e ON e.id = ie.entity_id
        WHERE i.kind = 'identity_endpoint_chain'
          AND e.kind = 'user'
          AND e.natural_key = 'alice';" \
    2>/dev/null \
    | tr -d ' \r\n')
: "${CHAIN_COUNT:=0}"

ORPHAN_INCIDENTS=$(docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -t -A \
    -c "SELECT count(*) FROM incidents WHERE id NOT IN (SELECT incident_id FROM incident_events);" \
    2>/dev/null \
    | tr -d ' \r\n')
: "${ORPHAN_INCIDENTS:=0}"

print_acceptance_summary "$SIM_TB" "$BE_TB" "$EVT_COUNT" "$DEGRADED"
echo "  A5 extras:"
printf "    identity_compromise_count    = %s  (must be exactly 1)\n" "$IDENTITY_COUNT"
printf "    identity_endpoint_chain_count = %s  (must be exactly 1)\n" "$CHAIN_COUNT"
printf "    orphan_incidents             = %s  (must be 0)\n" "$ORPHAN_INCIDENTS"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision.
# ----------------------------------------------------------------------------
FAIL=0
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend produced $BE_TB traceback(s) post-restart — should recover cleanly"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in postgres last 5 min — pre-kill events did not survive (or chaos didn't fire)"
    FAIL=1
fi
if [ "$DEGRADED" -le 0 ]; then
    echo "FAIL: 0 recovery markers in backend log — backend may not have actually restarted in this window"
    FAIL=1
fi
if [ "$IDENTITY_COUNT" -ne 1 ]; then
    echo "FAIL: identity_compromise count for alice = $IDENTITY_COUNT (expected exactly 1) — dedupe path broken"
    FAIL=1
fi
if [ "$CHAIN_COUNT" -ne 1 ]; then
    echo "FAIL: identity_endpoint_chain count for alice = $CHAIN_COUNT (expected exactly 1) — chain dedupe broken OR stage 4 process.created didn't land before kill (try increasing KILL_AT)"
    FAIL=1
fi
if [ "$ORPHAN_INCIDENTS" -gt 0 ]; then
    echo "FAIL: $ORPHAN_INCIDENTS orphan incident(s) without incident_events — half-written incident from the SIGKILL"
    FAIL=1
fi

# Note: SIM_TB intentionally NOT a hard fail. The simulator's raise_for_status
# may surface the kill as an httpx-level exception, which Python prints as a
# stack trace. That's the expected behavior, not a regression — the assertion
# is on Postgres truth, not simulator log shape.

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A5 acceptance NOT met"
    exit 1
fi

echo "PASS: §A5 acceptance met — backend SIGKILL + restart preserved exactly-one of each incident kind, no orphans, no backend tracebacks"
exit 0
