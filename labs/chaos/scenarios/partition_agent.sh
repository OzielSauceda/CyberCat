#!/usr/bin/env bash
# labs/chaos/scenarios/partition_agent.sh
#
# Phase 19.5 scenario A3: network-partition the cct-agent from the backend
# for 60s while sshd events are being generated into lab-debian. After
# the partition heals, assert that ≥80% of the partition-window events
# eventually land in the events table.
#
# Plan substitution: the original roadmap called for `iptables` to drop
# port 8000 from cct-agent. `iptables` requires CAP_NET_ADMIN which
# `ubuntu-latest` GH runners don't grant. Substituted with
# `docker network disconnect <net> compose-cct-agent-1` — the agent's
# HTTP client gets connection-refused / hangs, retries fire as designed,
# and the partition heals when we reconnect the agent to the network.
# Functionally equivalent at the container level.
#
# Acceptance bar is ≥80%, NOT 100%. The shipper at agent/cct_agent/shipper.py
# uses a bounded queue (drop-oldest on overflow) and gives up after 5 retries
# × exponential backoff capped at ~61s. A 60s partition is right at the edge
# of the retry budget — events shipped early in the partition can survive
# (their retry chain spans the partition); events fired deep in the
# partition window get dropped. ≥80% is the realistic floor.
#
# Test recipe:
#   1. Auto-detect compose network name + agent container name.
#   2. Truncate event/incident tables for clean assertion window.
#   3. Background a 90s emitter writing 1 sshd `Failed password` line/s
#      into lab-debian:/var/log/auth.log, each line tagged with a
#      unique user `chaosA3_NNN` so we can count distinct landings.
#   4. At PARTITION_AT (default 10s) — `docker network disconnect`.
#   5. After PARTITION_DURATION (default 60s) — `docker network connect`.
#   6. Wait for emitter to finish + DRAIN_SETTLE (default 30s) for the
#      shipper's retry queue to drain post-heal.
#   7. Count distinct chaosA3_* events in events table.
#   8. Compute acceptance ratio.
#
# Pass criteria:
#   - sim_tracebacks       == 0
#   - backend_tracebacks   == 0  (agent is "the sim" here, but its log goes
#                                  to backend_tracebacks bucket alongside
#                                  the backend's own log)
#   - event_count_5min     > 0   (some events landed)
#   - degraded_warnings    > 0   (shipper logged "ship failed" / "retries
#                                  exhausted" / "queue full" during partition)
#   - acceptance_ratio     ≥ 80% (chaosA3 events landed / chaosA3 events emitted)
#   - agent process still running after partition heal (no crash)
#
# Usage (after `bash start.sh`):
#   bash labs/chaos/scenarios/partition_agent.sh
#
# Override defaults via env vars:
#   PARTITION_AT=5 PARTITION_DURATION=30 EMIT_DURATION=60 \
#     bash labs/chaos/scenarios/partition_agent.sh
#
# CI equivalent: .github/workflows/chaos-partition.yml

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
: "${PARTITION_AT:=10}"          # seconds before disconnect
: "${PARTITION_DURATION:=60}"    # seconds the agent stays disconnected
: "${EMIT_DURATION:=90}"         # total seconds the emitter runs
: "${DRAIN_SETTLE:=30}"          # post-heal settle for shipper retry queue
: "${ACCEPTANCE_THRESHOLD_PCT:=80}"  # ≥ this % of emitted events must land
: "${SCENARIO_NAME:=partition_agent}"

trap 'cleanup_chaos_state' EXIT

echo "================================================================"
echo "  chaos scenario A3: partition_agent (docker network disconnect for ${PARTITION_DURATION}s)"
echo "  partition_at=${PARTITION_AT}s  emit_duration=${EMIT_DURATION}s"
echo "  drain_settle=${DRAIN_SETTLE}s  acceptance_threshold=${ACCEPTANCE_THRESHOLD_PCT}%"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pre-flight + auto-detect compose network and agent container.
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable — bring up the stack with 'bash start.sh' first"
    exit 1
fi

# Find the agent container name (compose project prefix may vary).
AGENT_CONTAINER=$(docker ps --format '{{.Names}}' \
    | grep -E '(^|-|/)cct-agent(-1)?$' \
    | head -1 \
    || true)
if [ -z "$AGENT_CONTAINER" ]; then
    echo "FAIL: could not find cct-agent container — is the agent profile up?"
    docker ps --format 'table {{.Names}}\t{{.Status}}'
    exit 1
fi
echo "[$(date +%T)] Detected agent container: $AGENT_CONTAINER"

# Find which network the agent is on. Pick the first non-`bridge`/`host` net.
AGENT_NETWORK=$(docker inspect "$AGENT_CONTAINER" \
    --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' \
    2>/dev/null \
    | grep -v -E '^(bridge|host|none)$' \
    | head -1 \
    || true)
if [ -z "$AGENT_NETWORK" ]; then
    echo "FAIL: could not detect agent's compose network from docker inspect"
    docker inspect "$AGENT_CONTAINER" --format '{{json .NetworkSettings.Networks}}' | head -c 500
    exit 1
fi
echo "[$(date +%T)] Detected agent network:   $AGENT_NETWORK"

# Find lab-debian container (where we inject sshd events).
LAB_CONTAINER=$(docker ps --format '{{.Names}}' \
    | grep -E '(^|-|/)lab-debian(-1)?$' \
    | head -1 \
    || true)
if [ -z "$LAB_CONTAINER" ]; then
    echo "FAIL: could not find lab-debian container — A3 emits sshd events into it"
    exit 1
fi
echo "[$(date +%T)] Detected lab container:   $LAB_CONTAINER"

# ----------------------------------------------------------------------------
# Truncate event/detection/incident tables for clean per-user counts.
# ----------------------------------------------------------------------------
echo "[$(date +%T)] Truncating tables for clean assertion window..."
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -c "
        TRUNCATE evidence_requests, blocked_observables, lab_sessions,
                 notes, incident_transitions, action_logs, actions,
                 incident_attack, incident_entities, incident_events,
                 incident_detections, incidents, detections,
                 event_entities, events, entities
                 RESTART IDENTITY CASCADE;
    " > /dev/null 2>&1 || true
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T redis redis-cli FLUSHDB > /dev/null 2>&1 || true

# ----------------------------------------------------------------------------
# Background emitter — writes one syntactically-valid `Failed password` line
# per second into lab-debian:/var/log/auth.log. Each line uses a unique
# user `chaosA3_NNN` for deterministic landing counting.
# ----------------------------------------------------------------------------
EMITTER_LOG="/tmp/cct_chaos_a3_emitter.log"
: > "$EMITTER_LOG"
EMITTED_COUNT_FILE="/tmp/cct_chaos_a3_emitted.count"
echo 0 > "$EMITTED_COUNT_FILE"

emit_sshd_events() {
    local i ts user ip line
    local emitted=0
    for i in $(seq 1 "$EMIT_DURATION"); do
        # Use UTC so the agent's sshd parser stores occurred_at consistent
        # with postgres now() (which is also UTC). Without -u the host's
        # local time goes into the auth.log line, the agent interprets it
        # as UTC, and events look hours-old to count_postgres_events_5min.
        ts=$(date -u '+%b %_d %H:%M:%S')
        user="chaosA3_$(printf '%03d' "$i")"
        ip="203.0.113.$((1 + (i % 254)))"
        line="$ts lab-debian sshd[$((20000 + i))]: Failed password for invalid user $user from $ip port $((50000 + i)) ssh2"
        if docker exec -i "$LAB_CONTAINER" sh -c "printf '%s\n' \"$line\" >> /var/log/auth.log" \
                >> "$EMITTER_LOG" 2>&1; then
            emitted=$((emitted + 1))
        fi
        sleep 1
    done
    echo "$emitted" > "$EMITTED_COUNT_FILE"
    echo "[$(date +%T)] emitter finished — emitted $emitted lines into lab-debian:/var/log/auth.log" >> "$EMITTER_LOG"
}

emit_sshd_events &
EMITTER_PID=$!
: "${EMITTER_PID:=0}"
echo "[$(date +%T)] Emitter PID=$EMITTER_PID firing 1 sshd line/s for ${EMIT_DURATION}s"

# ----------------------------------------------------------------------------
# The chaos: disconnect at PARTITION_AT, reconnect after PARTITION_DURATION.
# ----------------------------------------------------------------------------
sleep "$PARTITION_AT"

echo "----- disconnect cct-agent from $AGENT_NETWORK -----"
docker network disconnect "$AGENT_NETWORK" "$AGENT_CONTAINER" \
    || echo "WARN: docker network disconnect returned non-zero (already disconnected?)"

echo "[$(date +%T)] Agent partitioned. Sleeping ${PARTITION_DURATION}s..."
sleep "$PARTITION_DURATION"

echo "----- reconnect cct-agent to $AGENT_NETWORK -----"
docker network connect "$AGENT_NETWORK" "$AGENT_CONTAINER" \
    || echo "WARN: docker network connect returned non-zero (already connected?)"

# Wait for the emitter to finish.
if [ "$EMITTER_PID" -gt 0 ]; then
    wait "$EMITTER_PID" || true
fi

echo "[$(date +%T)] Settling ${DRAIN_SETTLE}s for shipper to drain its retry queue post-heal..."
sleep "$DRAIN_SETTLE"

# ----------------------------------------------------------------------------
# Capture logs.
# ----------------------------------------------------------------------------
BACKEND_LOG="/tmp/cct_chaos_a3_backend.log"
AGENT_LOG="/tmp/cct_chaos_a3_agent.log"
capture_backend_log "$BACKEND_LOG" 250
capture_agent_log "$AGENT_LOG" 250

echo "================================================================"
echo "  emitter log (last 30 lines)"
echo "================================================================"
tail -30 "$EMITTER_LOG" || true
echo "================================================================"
echo "  agent logs (last 250 lines)"
echo "================================================================"
cat "$AGENT_LOG" || true
echo "================================================================"
echo "  backend logs (last 250 lines)"
echo "================================================================"
cat "$BACKEND_LOG" || true
echo "================================================================"

# ----------------------------------------------------------------------------
# Counters.
# ----------------------------------------------------------------------------
SIM_TB=$(count_traceback_lines "$EMITTER_LOG")
BE_TB=$(count_traceback_lines "$BACKEND_LOG")
AGENT_TB=$(count_traceback_lines "$AGENT_LOG")
EVT_COUNT=$(count_postgres_events_5min)

# A3-specific degraded pattern: shipper failure / retry / queue full / drop
# log lines from the agent. These are the proof-of-chaos signal.
DEGRADED=$(count_degraded_warnings "$AGENT_LOG" \
    "ship queue full|max retries exhausted|backend rejected|RequestError|ConnectError|ReadTimeout|httpx")

# A3-specific acceptance: count distinct chaosA3 events in events table
# vs the count the emitter reports.
EMITTED_TOTAL=$(cat "$EMITTED_COUNT_FILE" 2>/dev/null | tr -d ' \r\n' || echo 0)
: "${EMITTED_TOTAL:=0}"

LANDED_TOTAL=$(docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -t -A \
    -c "SELECT count(DISTINCT (normalized->>'user'))
        FROM events
        WHERE normalized->>'user' LIKE 'chaosA3_%';" \
    2>/dev/null \
    | tr -d ' \r\n')
: "${LANDED_TOTAL:=0}"

# Compute acceptance ratio (integer percentage). Avoid div-by-zero.
if [ "$EMITTED_TOTAL" -gt 0 ]; then
    ACCEPTANCE_PCT=$(( (LANDED_TOTAL * 100) / EMITTED_TOTAL ))
else
    ACCEPTANCE_PCT=0
fi

# Agent process running check.
if docker ps --format '{{.Names}}' | grep -q "^${AGENT_CONTAINER}$"; then
    AGENT_RUNNING="yes"
else
    AGENT_RUNNING="NO"
fi

print_acceptance_summary "$SIM_TB" "$((BE_TB + AGENT_TB))" "$EVT_COUNT" "$DEGRADED"
echo "  A3 extras:"
printf "    emitted_total      = %s\n" "$EMITTED_TOTAL"
printf "    landed_total       = %s  (distinct chaosA3_* users in events)\n" "$LANDED_TOTAL"
printf "    acceptance_pct     = %s%%  (must be ≥ %s%%)\n" "$ACCEPTANCE_PCT" "$ACCEPTANCE_THRESHOLD_PCT"
printf "    agent_running      = %s  (must be 'yes')\n" "$AGENT_RUNNING"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision.
# ----------------------------------------------------------------------------
FAIL=0
if [ "$AGENT_TB" -gt 0 ]; then
    echo "FAIL: agent produced $AGENT_TB traceback(s) — should drop events with 'ship failed' log, not crash"
    FAIL=1
fi
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend produced $BE_TB traceback(s) during/after partition"
    FAIL=1
fi
if [ "$AGENT_RUNNING" != "yes" ]; then
    echo "FAIL: agent container is not running after partition heal"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in postgres last 5 min — agent didn't ship anything (or partition window was the entire test)"
    FAIL=1
fi
if [ "$DEGRADED" -le 0 ]; then
    echo "FAIL: 0 'ship failed / queue full / RequestError' lines in agent log — partition didn't actually hit the shipper (or pattern needs widening)"
    FAIL=1
fi
if [ "$EMITTED_TOTAL" -le 0 ]; then
    echo "FAIL: emitter reported 0 events emitted — likely lab-debian write failed"
    FAIL=1
fi
if [ "$ACCEPTANCE_PCT" -lt "$ACCEPTANCE_THRESHOLD_PCT" ]; then
    echo "FAIL: acceptance ${ACCEPTANCE_PCT}% < ${ACCEPTANCE_THRESHOLD_PCT}% — too many partition-window events were dropped"
    echo "      (see plan §A3 'Acceptance' — shipper has bounded retries; longer partitions WILL drop more)"
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A3 acceptance NOT met"
    exit 1
fi

echo "PASS: §A3 acceptance met — agent survived ${PARTITION_DURATION}s partition, ${ACCEPTANCE_PCT}% of events landed (≥${ACCEPTANCE_THRESHOLD_PCT}% threshold), no traceback"
exit 0
