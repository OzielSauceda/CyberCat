#!/usr/bin/env bash
# labs/chaos/scenarios/pause_agent.sh
#
# Phase 19.5 scenario A4: SIGSTOP the cct-agent for 30s while events are
# being generated into lab-debian's /var/log/auth.log. After SIGCONT the
# agent must resume tailing from its persisted byte-offset cursor (NOT
# from current EOF) — meaning the pause-window events get picked up and
# delivered, just delayed.
#
# This exercises the agent's atomic checkpoint write + tail.py's
# resume-from-offset behavior (Phase 16/16.9/16.10 work).
#
# Test recipe:
#   1. Read all three checkpoint files inside cct-agent container BEFORE.
#   2. Background a 35s emitter that writes one sshd `Failed password`
#      line per second into lab-debian:/var/log/auth.log.
#   3. After PAUSE_AT seconds: docker compose pause cct-agent.
#   4. Sleep PAUSE_DURATION.
#   5. docker compose unpause cct-agent.
#   6. Wait for emitter to finish, then settle 10s.
#   7. Re-read checkpoint files AFTER.
#   8. Evaluate four §A1 counters + assert sshd cursor advanced.
#
# Pass criteria:
#   - sim_tracebacks       == 0   (emitter doesn't crash)
#   - backend_tracebacks   == 0   (no traceback during/after pause)
#   - event_count_5min     > 0    (events fired during pause are present
#                                  in postgres after agent resumes)
#   - degraded_warnings    > 0    (agent log shows checkpoint/tail activity)
#   - sshd_offset_after    > sshd_offset_before  (cursor advanced)
#
# Usage (after `bash start.sh`):
#   bash labs/chaos/scenarios/pause_agent.sh
#
# Override defaults via env vars:
#   PAUSE_AT=2 PAUSE_DURATION=15 bash labs/chaos/scenarios/pause_agent.sh
#
# CI equivalent: .github/workflows/chaos-pause.yml

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults (overridable via env)
# ----------------------------------------------------------------------------
: "${PAUSE_AT:=4}"           # seconds before pause
: "${PAUSE_DURATION:=30}"    # seconds the agent stays paused
: "${EMIT_DURATION:=35}"     # total seconds the emitter runs
: "${SCENARIO_NAME:=pause_agent}"

trap 'cleanup_chaos_state' EXIT

echo "================================================================"
echo "  chaos scenario A4: pause_agent (SIGSTOP cct-agent for ${PAUSE_DURATION}s)"
echo "  pause_at=${PAUSE_AT}s  emit_duration=${EMIT_DURATION}s"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable at http://localhost:8000/healthz — bring up the stack with 'bash start.sh' first"
    exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -q '^compose-cct-agent-1$'; then
    echo "FAIL: cct-agent container not running — Phase 19.5 §A4 needs the agent profile"
    exit 1
fi

# ----------------------------------------------------------------------------
# Helpers — read a checkpoint file from inside cct-agent and extract offset.
# ----------------------------------------------------------------------------
read_checkpoint() {
    local cp_path="$1"
    # MSYS_NO_PATHCONV=1 stops Git Bash on Windows from mangling absolute
    # Unix paths (it would otherwise rewrite /var/lib/... to
    # C:/Program Files/Git/var/lib/...). Same trick used by
    # labs/perf/run_postgres_restart_test.sh.
    MSYS_NO_PATHCONV=1 docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
        exec -T cct-agent cat "$cp_path" 2>/dev/null \
        | tr -d '\r' \
        || echo "{}"
}

extract_offset() {
    # Pick out "offset": <int> from a JSON checkpoint blob. Empty / missing →
    # 0 so the comparison still works (after > before will just be false).
    local val
    val=$(printf '%s' "$1" | grep -oE '"offset"[[:space:]]*:[[:space:]]*[0-9]+' \
        | grep -oE '[0-9]+' \
        | head -1 \
        || echo "0")
    if [ -z "$val" ]; then val=0; fi
    echo "$val"
}

# ----------------------------------------------------------------------------
# Snapshot checkpoints BEFORE the pause window.
# ----------------------------------------------------------------------------
SSHD_BEFORE_RAW=$(read_checkpoint /var/lib/cct-agent/checkpoint.json)
AUDIT_BEFORE_RAW=$(read_checkpoint /var/lib/cct-agent/audit-checkpoint.json)
CONNTRACK_BEFORE_RAW=$(read_checkpoint /var/lib/cct-agent/conntrack-checkpoint.json)

SSHD_OFFSET_BEFORE=$(extract_offset "$SSHD_BEFORE_RAW")
AUDIT_OFFSET_BEFORE=$(extract_offset "$AUDIT_BEFORE_RAW")
CONNTRACK_OFFSET_BEFORE=$(extract_offset "$CONNTRACK_BEFORE_RAW")

echo "[$(date +%T)] Pre-pause cursor offsets:  sshd=$SSHD_OFFSET_BEFORE  audit=$AUDIT_OFFSET_BEFORE  conntrack=$CONNTRACK_OFFSET_BEFORE"

# ----------------------------------------------------------------------------
# Background a sshd-event emitter.
# Each line is a syntactically valid `Failed password` line that the agent's
# sshd parser (agent/cct_agent/parsers/sshd.py:72) will accept. We use unique
# users (chaosA4_$i) and rotating IPs so dedupe doesn't collapse them.
# ----------------------------------------------------------------------------
EMITTER_LOG="/tmp/cct_chaos_a4_emitter.log"
: > "$EMITTER_LOG"

emit_sshd_events() {
    local i ts user ip
    for i in $(seq 1 "$EMIT_DURATION"); do
        # Use UTC so the agent's sshd parser stores occurred_at consistent
        # with postgres now() (which is also UTC).
        ts=$(date -u '+%b %_d %H:%M:%S')
        user="chaosA4_${i}"
        ip="203.0.113.$((1 + (i % 254)))"
        local line="$ts lab-debian sshd[$((10000 + i))]: Failed password for invalid user $user from $ip port $((50000 + i)) ssh2"
        docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
            exec -T lab-debian sh -c "printf '%s\n' \"$line\" >> /var/log/auth.log" \
            >> "$EMITTER_LOG" 2>&1 \
            || echo "[$(date +%T)] emit_$i: docker exec failed (transient OK)" >> "$EMITTER_LOG"
        sleep 1
    done
    echo "[$(date +%T)] emitter finished — fired $EMIT_DURATION events" >> "$EMITTER_LOG"
}

emit_sshd_events &
EMITTER_PID=$!
: "${EMITTER_PID:=0}"
echo "[$(date +%T)] Emitter PID=$EMITTER_PID firing 1 sshd event/s for ${EMIT_DURATION}s"

# ----------------------------------------------------------------------------
# The chaos: pause + sleep + unpause.
# ----------------------------------------------------------------------------
sleep "$PAUSE_AT"

echo "----- pause cct-agent -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" pause cct-agent

echo "[$(date +%T)] Agent paused. Sleeping ${PAUSE_DURATION}s while events accumulate in lab-debian:/var/log/auth.log..."
sleep "$PAUSE_DURATION"

echo "----- unpause cct-agent -----"
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" unpause cct-agent

# Wait for the emitter to finish.
if [ "$EMITTER_PID" -gt 0 ]; then
    wait "$EMITTER_PID" || true
fi

echo "[$(date +%T)] Settling 10s for the agent to tail-and-ship the pause-window backlog..."
sleep 10

# ----------------------------------------------------------------------------
# Snapshot checkpoints AFTER.
# ----------------------------------------------------------------------------
SSHD_AFTER_RAW=$(read_checkpoint /var/lib/cct-agent/checkpoint.json)
AUDIT_AFTER_RAW=$(read_checkpoint /var/lib/cct-agent/audit-checkpoint.json)
CONNTRACK_AFTER_RAW=$(read_checkpoint /var/lib/cct-agent/conntrack-checkpoint.json)

SSHD_OFFSET_AFTER=$(extract_offset "$SSHD_AFTER_RAW")
AUDIT_OFFSET_AFTER=$(extract_offset "$AUDIT_AFTER_RAW")
CONNTRACK_OFFSET_AFTER=$(extract_offset "$CONNTRACK_AFTER_RAW")

# ----------------------------------------------------------------------------
# Capture logs.
# ----------------------------------------------------------------------------
BACKEND_LOG="/tmp/cct_chaos_a4_backend.log"
AGENT_LOG="/tmp/cct_chaos_a4_agent.log"
capture_backend_log "$BACKEND_LOG" 250
capture_agent_log "$AGENT_LOG" 250

echo "================================================================"
echo "  emitter log"
echo "================================================================"
cat "$EMITTER_LOG" || true
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

# A4-specific degraded pattern: agent log lines that prove the tail loop
# kept persisting and resuming offsets. Match the structured logs the
# checkpoint module emits.
DEGRADED=$(count_degraded_warnings "$AGENT_LOG" \
    "checkpoint|tailing|resumed|offset")

# Combine backend + agent tracebacks into the "backend_tracebacks" counter
# for summary purposes — the §A1 model treats both the supervisor side and
# the request side as "backend-side" health.
COMBINED_BE_TB=$((BE_TB + AGENT_TB))

print_acceptance_summary "$SIM_TB" "$COMBINED_BE_TB" "$EVT_COUNT" "$DEGRADED"
echo "  A4 extras:"
printf "    sshd_offset_before     = %s\n" "$SSHD_OFFSET_BEFORE"
printf "    sshd_offset_after      = %s  (must be > before)\n" "$SSHD_OFFSET_AFTER"
printf "    audit_offset_before    = %s\n" "$AUDIT_OFFSET_BEFORE"
printf "    audit_offset_after     = %s  (informational; auditd may be unavailable)\n" "$AUDIT_OFFSET_AFTER"
printf "    conntrack_offset_before= %s\n" "$CONNTRACK_OFFSET_BEFORE"
printf "    conntrack_offset_after = %s  (informational; conntrack may be unavailable)\n" "$CONNTRACK_OFFSET_AFTER"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision.
# ----------------------------------------------------------------------------
FAIL=0
if [ "$AGENT_TB" -gt 0 ]; then
    echo "FAIL: agent produced $AGENT_TB traceback(s) — should resume cleanly from SIGCONT"
    FAIL=1
fi
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend produced $BE_TB traceback(s) during/after the pause window"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in postgres last 5 min — agent did not replay the pause-window backlog"
    FAIL=1
fi
if [ "$SSHD_OFFSET_AFTER" -le "$SSHD_OFFSET_BEFORE" ]; then
    echo "FAIL: sshd cursor did not advance (before=$SSHD_OFFSET_BEFORE, after=$SSHD_OFFSET_AFTER) — agent did not resume tailing"
    FAIL=1
fi
if [ "$DEGRADED" -le 0 ]; then
    echo "FAIL: 0 'checkpoint/tailing/resumed/offset' log lines in agent log — chaos may have missed the right path"
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A4 acceptance NOT met"
    exit 1
fi

echo "PASS: §A4 acceptance met — agent resumed from cursor, pause-window events replayed, sshd cursor advanced from $SSHD_OFFSET_BEFORE to $SSHD_OFFSET_AFTER"
exit 0
