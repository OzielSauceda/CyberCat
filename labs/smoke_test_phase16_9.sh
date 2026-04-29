#!/usr/bin/env bash
# Phase 16.9 smoke test — auditd-driven process telemetry
# Run from the repo root: bash labs/smoke_test_phase16_9.sh
#
# Prereq: ./start.sh (default profile = core+agent in Phase 16.6)
# Honours labs/.smoke-env for SMOKE_API_TOKEN if AUTH_REQUIRED=true.
#
# Verifies the auditd path end-to-end:
#   synthetic auditd records → /var/log/audit/audit.log (lab_logs volume)
#     → cct-agent auditd source (tail + AuditdParser + TrackedProcesses)
#     → POST /v1/events/raw (source=direct, kind=process.created/exited)
#     → backend ingest + py.process.suspicious_child detection
#     → endpoint_compromise incident
#
# Why synthetic injection: Docker Desktop on Windows (WSL2 backend) does not
# expose the kernel audit netlink socket to containers, so auditd inside
# lab-debian cannot start (auditctl returns EPERM). The agent code path is
# identical regardless of whether the audit lines come from the real kernel
# or from a here-doc — synthetic lines validate parse + ship + detect end-to-end.
# On a Linux host where kernel audit IS available, the same script works
# unchanged because the agent just tails whatever lines arrive at the file.
set -euo pipefail

API="${CYBERCAT_API:-http://localhost:8000}"
COMPOSE_FILE="infra/compose/docker-compose.yml"
PY="python"
command -v python3 >/dev/null 2>&1 && PY="python3" || true

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
RESET='\033[0m'

[ -f "labs/.smoke-env" ] && source "labs/.smoke-env" || true
[ -n "${SMOKE_API_TOKEN:-}" ] && AUTH_HEADER=(-H "Authorization: Bearer $SMOKE_API_TOKEN") || AUTH_HEADER=()

PASSES=0
FAILURES=0

pass()   { echo -e "${GREEN}PASS${RESET} $1"; PASSES=$((PASSES + 1)); }
fail()   { echo -e "${RED}FAIL${RESET} $1"; FAILURES=$((FAILURES + 1)); }
warn()   { echo -e "${YELLOW}WARN${RESET} $1"; }
header() { echo -e "\n${BOLD}--- $1 ---${RESET}"; }

# ---------------------------------------------------------------------------
# 1. Containers up + Wazuh stays dormant
# ---------------------------------------------------------------------------
header "Containers"
http_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/healthz")
[ "$http_status" = "200" ] && pass "Backend /healthz returns 200" \
    || { fail "Backend not healthy (HTTP $http_status) — run ./start.sh first"; exit 1; }

for c in compose-cct-agent-1 compose-lab-debian-1; do
    if docker ps --format "{{.Names}}" | grep -q "^${c}$"; then
        pass "${c} is running"
    else
        fail "${c} is not running — run ./start.sh first"
        exit 1
    fi
done

if docker ps --format "{{.Names}}" | grep -qE "^compose-wazuh-(manager|indexer)-1$"; then
    warn "Wazuh containers running — Phase 16 default is agent-only (--profile wazuh active?)"
else
    pass "Wazuh containers NOT running (default agent-only profile)"
fi

# ---------------------------------------------------------------------------
# 2. Ensure audit.log file exists (so agent picks up the source on next restart)
# ---------------------------------------------------------------------------
header "Audit log file"
MSYS_NO_PATHCONV=1 docker exec compose-lab-debian-1 bash -c \
    'mkdir -p /var/log/audit && touch /var/log/audit/audit.log && chmod 644 /var/log/audit/audit.log' \
    && pass "audit.log exists in lab-debian (/var/log/audit/audit.log)" \
    || { fail "could not create audit.log"; exit 1; }

# ---------------------------------------------------------------------------
# 3. Restart cct-agent so it (re)evaluates the audit source on startup
# ---------------------------------------------------------------------------
header "Agent restart for source pickup"
docker compose -f "${COMPOSE_FILE}" restart cct-agent > /dev/null 2>&1
echo "Waiting for agent banner..."

# Poll for the readiness line for up to 30s
SAW_BANNER=""
for _ in $(seq 1 30); do
    if docker logs compose-cct-agent-1 2>&1 | grep -q "agent ready, tailing.*audit.log"; then
        SAW_BANNER="yes"
        break
    fi
    sleep 1
done

if [ -n "$SAW_BANNER" ]; then
    pass "Agent banner shows audit.log being tailed"
    docker logs compose-cct-agent-1 --tail 5 2>&1 | grep -E "agent ready|sshd source|auditd source" || true
else
    fail "Agent did not log 'tailing ... audit.log' within 30s"
    docker logs compose-cct-agent-1 --tail 30 2>&1
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Truncate DB + flush Redis for clean assertion window
# ---------------------------------------------------------------------------
header "Setup: truncate DB and flush Redis"
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -c "
      TRUNCATE evidence_requests, blocked_observables, lab_sessions,
               notes, incident_transitions, action_logs, actions,
               incident_attack, incident_entities, incident_events,
               incident_detections, incidents, detections,
               event_entities, events, entities, lab_assets
      CASCADE;
    " > /dev/null \
    && pass "DB truncated" || warn "Could not truncate DB — continuing"

docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null \
    && pass "Redis flushed" || warn "Redis flush failed — continuing"

# ---------------------------------------------------------------------------
# 5. Inject synthetic auditd records simulating an Office→shell spawn pattern
# ---------------------------------------------------------------------------
header "Inject synthetic auditd records"
TS=$(date +%s).000
PARENT_PID=10001
CHILD_PID=10002
EID_PARENT=900001
EID_CHILD=900002
EID_EXIT=900003

# image fields are bare basenames so the existing py.process.suspicious_child
# detector (which uses set membership over {winword.exe, cmd.exe, ...}) fires.
# Real auditd typically ships full paths; the agent code path is the same.
INJECT=$(cat <<EOF
type=SYSCALL msg=audit(${TS}:${EID_PARENT}): arch=c000003e syscall=59 success=yes exit=0 a0=55f0 a1=55f1 a2=0 a3=0 items=2 ppid=1 pid=${PARENT_PID} auid=1000 uid=1000 gid=1000 euid=1000 suid=1000 fsuid=1000 egid=1000 sgid=1000 fsgid=1000 tty=pts0 ses=1 comm="winword.exe" exe="winword.exe" subj=unconfined key="cybercat_exec"
type=EXECVE msg=audit(${TS}:${EID_PARENT}): argc=1 a0="winword.exe"
type=EOE msg=audit(${TS}:${EID_PARENT}):
type=SYSCALL msg=audit(${TS}:${EID_CHILD}): arch=c000003e syscall=59 success=yes exit=0 a0=55f2 a1=55f3 a2=0 a3=0 items=2 ppid=${PARENT_PID} pid=${CHILD_PID} auid=1000 uid=1000 gid=1000 euid=1000 suid=1000 fsuid=1000 egid=1000 sgid=1000 fsgid=1000 tty=pts0 ses=1 comm="cmd.exe" exe="cmd.exe" subj=unconfined key="cybercat_exec"
type=EXECVE msg=audit(${TS}:${EID_CHILD}): argc=2 a0="cmd.exe" a1="/c whoami"
type=EOE msg=audit(${TS}:${EID_CHILD}):
type=SYSCALL msg=audit(${TS}:${EID_EXIT}): arch=c000003e syscall=231 success=yes exit=0 a0=0 a1=0 a2=0 a3=0 items=0 ppid=${PARENT_PID} pid=${CHILD_PID} auid=1000 uid=1000 gid=1000 euid=1000 suid=1000 fsuid=1000 egid=1000 sgid=1000 fsgid=1000 tty=pts0 ses=1 comm="cmd.exe" exe="cmd.exe" subj=unconfined key="cybercat_exit"
type=EOE msg=audit(${TS}:${EID_EXIT}):
EOF
)

# Append into the lab_logs-shared audit.log. We use bash inside the container
# so the synthetic content appears on the same path the agent tails.
MSYS_NO_PATHCONV=1 docker exec -i compose-lab-debian-1 bash -c \
    'cat >> /var/log/audit/audit.log' <<<"$INJECT" \
    && pass "Injected 8 audit records (1 parent execve + 1 child execve + 1 child exit)" \
    || { fail "could not write to audit.log"; exit 1; }

echo "Waiting 15s for agent → backend → detection → correlation..."
sleep 15

# ---------------------------------------------------------------------------
# 6. process.created events arrived (source=direct)
# ---------------------------------------------------------------------------
header "Events: process.created"
EV_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?source=direct&kind=process.created&limit=50") \
    || { fail "GET /v1/events?kind=process.created failed"; exit 1; }
EV_COUNT=$(echo "$EV_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

if [ "$EV_COUNT" -ge 2 ]; then
    pass "Backend has $EV_COUNT direct process.created events (>=2: parent + child)"
else
    fail "Expected >=2 direct process.created events, got $EV_COUNT"
    docker logs compose-cct-agent-1 --tail 30 2>&1
    exit 1
fi

# ---------------------------------------------------------------------------
# 7. process.exited event arrived (source=direct)
# ---------------------------------------------------------------------------
header "Events: process.exited"
EX_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?source=direct&kind=process.exited&limit=50") \
    || { fail "GET /v1/events?kind=process.exited failed"; exit 1; }
EX_COUNT=$(echo "$EX_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

if [ "$EX_COUNT" -ge 1 ]; then
    pass "Backend has $EX_COUNT direct process.exited event(s) (matched against tracked PID)"
else
    fail "Expected >=1 direct process.exited event, got $EX_COUNT"
    exit 1
fi

# ---------------------------------------------------------------------------
# 8. py.process.suspicious_child detection fired
# ---------------------------------------------------------------------------
header "Detection: py.process.suspicious_child"
DET_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/detections?rule_id=py.process.suspicious_child&limit=10") \
    || { fail "GET /v1/detections failed"; exit 1; }
DET_COUNT=$(echo "$DET_RESP" | $PY -c '
import json, sys
data = json.load(sys.stdin)
items = data.get("items", data) if isinstance(data, dict) else data
print(len(items))
')
if [ "$DET_COUNT" -ge 1 ]; then
    pass "py.process.suspicious_child fired ($DET_COUNT row(s))"
else
    fail "py.process.suspicious_child did not fire"
    echo "DEBUG: detections response head:"
    echo "$DET_RESP" | head -c 800
    exit 1
fi

# ---------------------------------------------------------------------------
# 9. endpoint_compromise incident opened
# ---------------------------------------------------------------------------
header "Incident: endpoint_compromise"
INC_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents?kind=endpoint_compromise&limit=10") \
    || { fail "GET /v1/incidents failed"; exit 1; }
INC_COUNT=$(echo "$INC_RESP" | $PY -c 'import json,sys; print(len(json.load(sys.stdin)["items"]))')
if [ "$INC_COUNT" -ge 1 ]; then
    pass "endpoint_compromise incident opened from agent-sourced events ($INC_COUNT)"
else
    fail "Expected >=1 endpoint_compromise incident, got 0"
    echo "DEBUG: all incidents:"
    curl -s "${AUTH_HEADER[@]}" "${API}/v1/incidents?limit=20" | $PY -m json.tool 2>/dev/null | head -40
    exit 1
fi

# ---------------------------------------------------------------------------
# 10. Wazuh path stays dormant (no regression to Phase 16.6)
# Pass condition: Wazuh either disabled in config OR not reachable.
# Either way, agent-sourced events drove the whole pipeline (asserted above).
# ---------------------------------------------------------------------------
header "Wazuh dormant"
WZ_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/wazuh/status") || true
WZ_STATUS=$(echo "$WZ_RESP" | $PY -c '
import json, sys
d = json.load(sys.stdin)
print(("disabled" if not d.get("enabled") else
       "unreachable" if not d.get("reachable") else "active"))
' 2>/dev/null || echo "?")
case "$WZ_STATUS" in
    disabled)    pass "Wazuh bridge disabled in config (no regression)" ;;
    unreachable) pass "Wazuh containers not running — bridge dormant (no regression)" ;;
    *)           fail "Wazuh path is unexpectedly active: $WZ_RESP" ;;
esac

# ---------------------------------------------------------------------------
# 11. Audit checkpoint advanced
# ---------------------------------------------------------------------------
header "Audit checkpoint"
CP_JSON=$(MSYS_NO_PATHCONV=1 docker exec compose-cct-agent-1 \
    cat /var/lib/cct-agent/audit-checkpoint.json 2>&1 || echo "MISSING")
if [ "$CP_JSON" = "MISSING" ] || ! echo "$CP_JSON" | grep -q "offset"; then
    fail "Audit checkpoint missing or malformed: $CP_JSON"
else
    OFFSET=$(echo "$CP_JSON" | $PY -c 'import json,sys; print(json.load(sys.stdin)["offset"])')
    if [ "$OFFSET" -gt 0 ]; then
        pass "Audit checkpoint advanced (offset=$OFFSET)"
    else
        fail "Audit checkpoint offset is 0 — agent has not advanced"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Phase 16.9 smoke test complete: ${GREEN}${PASSES} passed${RESET}, ${RED}${FAILURES} failed${RESET}"
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1
