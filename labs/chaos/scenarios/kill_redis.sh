#!/usr/bin/env bash
# labs/chaos/scenarios/kill_redis.sh
#
# Scenario A1 — Kill Redis mid-simulator-run.
#
# What it tests:
#   Kills the Redis container ~4 s into a simulator run, holds it dead for
#   25 s, then restores it. Verifies that safe_redis()
#   (backend/app/db/redis_state.py) and EventBus._supervisor()
#   (backend/app/streaming/bus.py:97-123) keep the ingest path alive when
#   Redis disappears abruptly — events keep landing in Postgres and the
#   resilience layer's degraded-mode log line fires.
#
# How to run (stack must already be up via 'bash start.sh'):
#   bash labs/chaos/scenarios/kill_redis.sh
#
#   Override defaults via env vars:
#     SPEED=0.2 KILL_AT=6 RESTORE_AFTER=30 bash labs/chaos/scenarios/kill_redis.sh
#
# Four §A1 acceptance counters:
#   1. sim_tracebacks       == 0   (simulator degraded gracefully; never raised)
#   2. backend_tracebacks   == 0   (safe_redis caught every redis call cleanly)
#   3. event_count_5min     > 0    (ingest survived; events landed in Postgres)
#   4. degraded_warnings    > 0    (redis_degraded / EventBus consumer crashed fired)
#      pattern: "redis_degraded|redis_state=unavailable|degraded mode|EventBus consumer crashed"
#
# GH Actions equivalent: .github/workflows/chaos-redis.yml
#   This script is the local host-runnable sibling of that workflow.
#   Both source labs/chaos/lib/evaluate.sh so the four counters are
#   computed identically on CI (ubuntu-latest) and on the operator's machine.
#   The workflow is NOT modified by this script — it stays as the CI gate.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults — match the chaos-redis.yml workflow inputs exactly.
# Override via env vars before running the script.
# ----------------------------------------------------------------------------
: "${SPEED:=0.1}"
: "${KILL_AT:=4}"
: "${RESTORE_AFTER:=25}"

# ----------------------------------------------------------------------------
# Token — required to drive the simulator from the host.
# read_token_from_env reads CCT_AGENT_TOKEN from infra/compose/.env.
# ----------------------------------------------------------------------------
TOKEN=$(read_token_from_env)
if [ -z "$TOKEN" ]; then
    echo "FAIL: CCT_AGENT_TOKEN is empty — run 'bash start.sh' first to provision the token"
    exit 1
fi

# Defensive trap: calls cleanup_chaos_state on any exit so a partial run
# (Ctrl-C, script error mid-chaos) doesn't leave Redis dead. Defined in
# labs/chaos/lib/evaluate.sh — already knows to restart redis if missing.
trap 'cleanup_chaos_state' EXIT

echo "================================================================"
echo "  chaos scenario A1: kill_redis"
echo "  speed=$SPEED  kill_at=${KILL_AT}s  restore_after=${RESTORE_AFTER}s"
echo "================================================================"

# Pre-flight: stack must be up before we start injecting chaos.
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable at http://localhost:8000/healthz — bring up the stack with 'bash start.sh' first"
    exit 1
fi
echo "[$(date +%T)] Pre-flight OK."

# ----------------------------------------------------------------------------
# Start the simulator in the background.
#
# --no-verify because the §A1 acceptance bar is graceful degradation, not
# "incident tree forms perfectly during chaos." Events fired while Redis is
# dead miss correlation (the correlator needs Redis windowed state), which
# is the documented degraded behaviour, not a failure. See chaos-redis.yml
# header for full rationale.
# ----------------------------------------------------------------------------
python -m labs.simulator \
    --scenario credential_theft_chain \
    --speed "$SPEED" \
    --api http://localhost:8000 \
    --token "$TOKEN" \
    --no-verify \
    > sim.log 2>&1 &
SIM_PID=$!
: "${SIM_PID:=0}"
echo "[$(date +%T)] Simulator backgrounded  PID=$SIM_PID. Sleeping ${KILL_AT}s before redis kill..."

sleep "$KILL_AT"

# ----------------------------------------------------------------------------
# The chaos: kill Redis (SIGKILL — abrupt, no SIGTERM grace window).
# From safe_redis's perspective the connection just disappears mid-call,
# which is the worst-case failure mode we're testing.
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
echo "[$(date +%T)] Redis restored. Waiting for simulator to finish..."

# Wait for simulator completion. Exit code is informational — the four §A1
# counters below are the pass/fail criteria, not the simulator's exit code.
: "${SIM_PID:=0}"
if [ "$SIM_PID" -gt 0 ]; then
    wait "$SIM_PID" || true
    SIM_EXIT=$?
else
    SIM_EXIT=99
fi
echo "[$(date +%T)] Simulator done.  SIM_EXIT=$SIM_EXIT (informational)"

# ----------------------------------------------------------------------------
# Capture and print logs inline so the operator can see the chaos evidence
# directly in the terminal output without inspecting separate files.
# ----------------------------------------------------------------------------
echo "================================================================"
echo "  sim.log (full)"
echo "================================================================"
cat sim.log || true
echo "================================================================"
echo "  end sim.log"
echo "================================================================"

echo "================================================================"
echo "  backend logs (last 250 lines)"
echo "================================================================"
capture_backend_log backend.log 250
cat backend.log || true
echo "================================================================"
echo "  end backend logs"
echo "================================================================"

# ----------------------------------------------------------------------------
# Compute the four §A1 counters using the shared helpers from lib/evaluate.sh.
# These same helpers run on CI inside chaos-redis.yml — single source of truth.
# ----------------------------------------------------------------------------
SIM_TB=$(count_traceback_lines sim.log)
BE_TB=$(count_traceback_lines backend.log)
EVT_COUNT=$(count_postgres_events_5min)

# A1 degraded-mode pattern — matches docs/phase-19.5-plan.md §A1 verbatim.
# Any one of these log shapes proves the resilience layer engaged:
#   redis_degraded           — safe_redis() log emit (redis_state.py:61)
#   redis_state=unavailable  — structured field variant
#   degraded mode            — human-readable fallback phrase
#   EventBus consumer crashed — EventBus._supervisor() restart log (bus.py:97-123)
DEGRADED=$(count_degraded_warnings backend.log \
    "redis_degraded|redis_state=unavailable|degraded mode|EventBus consumer crashed")

print_acceptance_summary "$SIM_TB" "$BE_TB" "$EVT_COUNT" "$DEGRADED"
echo "  simulator_exit     = $SIM_EXIT  (informational)"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision — strict §A1 criteria (matches chaos-redis.yml exactly).
# ----------------------------------------------------------------------------
FAIL=0
if [ "$SIM_TB" -gt 0 ]; then
    echo "FAIL: sim.log contains $SIM_TB traceback(s) — simulator should degrade gracefully through the Redis kill"
    FAIL=1
fi
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend.log contains $BE_TB traceback(s) — safe_redis() should swallow every redis call cleanly"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in Postgres last 5 min — ingest path didn't survive the Redis kill"
    FAIL=1
fi
if [ "$DEGRADED" -le 0 ]; then
    echo "FAIL: degraded_warnings=0 — safe_redis/EventBus supervisor didn't fire (or the kill window missed every Redis call). Tune KILL_AT/RESTORE_AFTER or verify the safe_redis log emit is wired."
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A1 acceptance NOT met — see counters above"
    exit 1
fi

echo "PASS: §A1 acceptance met — ${DEGRADED} degraded warning(s), ${EVT_COUNT} events in last 5min, 0 tracebacks"
exit 0
