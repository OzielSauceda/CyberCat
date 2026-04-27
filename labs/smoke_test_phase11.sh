#!/usr/bin/env bash
# Phase 11 smoke test — Wazuh Active Response end-to-end
# Requires: docker compose --profile wazuh stack running, WAZUH_AR_ENABLED=true in .env
#
# Usage:
#   ./labs/smoke_test_phase11.sh              # happy path
#   ./labs/smoke_test_phase11.sh --cleanup    # flush iptables, restart lab-debian
#   ./labs/smoke_test_phase11.sh --test-negative  # stop manager, expect partial

set -euo pipefail

API="${CYBERCAT_API:-http://localhost:8000}"
COMPOSE="docker compose -f infra/compose/docker-compose.yml --profile wazuh"
PASS=0
FAIL=0

info()  { echo "[INFO]  $*"; }
ok()    { echo "[PASS]  $*"; PASS=$((PASS+1)); }
fail()  { echo "[FAIL]  $*"; FAIL=$((FAIL+1)); }
check() { [ "$1" = "$2" ] && ok "$3" || fail "$3: expected '$2' got '$1'"; }

# ---------------------------------------------------------------------------
# Cleanup mode
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--cleanup" ]]; then
    info "Flushing iptables on lab-debian..."
    $COMPOSE exec lab-debian iptables -F || true
    info "Restarting lab-debian..."
    $COMPOSE restart lab-debian
    info "Cleanup done."
    exit 0
fi

# ---------------------------------------------------------------------------
# Negative path: manager down
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--test-negative" ]]; then
    info "Stopping wazuh-manager for negative path test..."
    $COMPOSE stop wazuh-manager

    r=$(curl -sf -X POST "$API/v1/lab/assets" \
        -H "Content-Type: application/json" \
        -d '{"kind":"host","natural_key":"lab-debian"}' 2>/dev/null || true)

    inc_id=$(curl -sf -X POST "$API/v1/events/raw" \
        -H "Content-Type: application/json" \
        -d '{"source":"seeder","kind":"auth.failed","occurred_at":"2026-04-23T09:00:00Z","raw":{},"normalized":{"user":"alice","source_ip":"1.2.3.4","auth_type":"ssh"},"dedupe_key":"neg-fail-1"}' 2>/dev/null | \
        python3 -c "import sys,json; print('ok')" && \
        curl -sf "$API/v1/incidents?limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'])")

    prop=$(curl -sf -X POST "$API/v1/responses" \
        -H "Content-Type: application/json" \
        -d "{\"incident_id\":\"$inc_id\",\"kind\":\"quarantine_host_lab\",\"params\":{\"host\":\"lab-debian\"}}")
    action_id=$(echo "$prop" | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['id'])")

    exec_r=$(curl -sf -X POST "$API/v1/responses/$action_id/execute")
    status=$(echo "$exec_r" | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['status'])")
    check "$status" "partial" "negative: action.status is partial when manager down"

    info "Restarting wazuh-manager..."
    $COMPOSE start wazuh-manager
    echo ""
    echo "Results: PASS=$PASS FAIL=$FAIL"
    exit $FAIL
fi

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

# 0. Pre-flight: remove stale lab-debian agent registrations from manager so the
#    current container can auto-enroll without a "Duplicate agent name" error.
info "Pre-flight: removing stale lab-debian agent registrations..."
_TOKEN=$(curl -sk -u "wazuh-wui:${WAZUH_MANAGER_PASSWORD:-wazuh-wui}" \
    "https://localhost:55000/security/user/authenticate" 2>/dev/null | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('token',''))" 2>/dev/null || echo "")
if [ -n "$_TOKEN" ]; then
    _IDS=$(curl -sk -H "Authorization: Bearer $_TOKEN" \
        "https://localhost:55000/agents?name=lab-debian" 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); ids=[a['id'] for a in d.get('data',{}).get('affected_items',[])]; print(','.join(ids))" 2>/dev/null || echo "")
    if [ -n "$_IDS" ]; then
        curl -sk -X DELETE -H "Authorization: Bearer $_TOKEN" \
            "https://localhost:55000/agents?agents_list=${_IDS}&status=all&older_than=0s" > /dev/null 2>&1 || true
        info "Deleted stale agents: $_IDS — restarting lab-debian..."
        $COMPOSE restart lab-debian
    fi
fi
# Flush stale agent_id Redis cache so agent_lookup picks up the new enrollment
docker exec compose-redis-1 redis-cli del "cybercat:wazuh_agent:lab-debian" > /dev/null 2>&1 || true

# 1. Wait for wazuh-manager healthy AND lab-debian enrolled
info "Waiting for wazuh-manager healthy and lab-debian enrolled (max 60s)..."
ENROLLED=false
for i in $(seq 1 45); do
    token=$(curl -sk -u "wazuh-wui:${WAZUH_MANAGER_PASSWORD:-wazuh-wui}" \
        "https://localhost:55000/security/user/authenticate" 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('token',''))" 2>/dev/null || echo "")
    result=$(curl -sk -H "Authorization: Bearer $token" \
        "https://localhost:55000/agents?name=lab-debian&status=active" 2>/dev/null || echo '{}')
    count=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('total_affected_items',0))" 2>/dev/null || echo 0)
    if [ "$count" -ge 1 ]; then
        ENROLLED=true
        ok "lab-debian enrolled in wazuh-manager"
        break
    fi
    sleep 2
done
[ "$ENROLLED" = "true" ] || { fail "lab-debian not active after 90s"; exit 1; }

# Wait for the Wazuh agent config-receive restart cycle to complete.
# On first connect, wazuh-agentd self-restarts (via restart.sh) to apply the
# shared config from the manager (~8s). Without this wait, AR dispatches
# hit the "agent is not active" window and fail.
info "Waiting 20s for agent config-receive restart cycle to settle..."
sleep 20

# Confirm the agent is still active after the restart cycle
_STAB_TOKEN=$(curl -sk -u "wazuh-wui:${WAZUH_MANAGER_PASSWORD:-wazuh-wui}" \
    "https://localhost:55000/security/user/authenticate" 2>/dev/null | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('token',''))" 2>/dev/null || echo "")
_STAB_COUNT=$(curl -sk -H "Authorization: Bearer $_STAB_TOKEN" \
    "https://localhost:55000/agents?name=lab-debian&status=active" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('total_affected_items',0))" 2>/dev/null || echo 0)
if [ "$_STAB_COUNT" -ge 1 ]; then
    ok "lab-debian still active after stabilization wait"
else
    fail "lab-debian went inactive after restart cycle — aborting"
    exit 1
fi

# 2. Register lab-debian as a lab asset
curl -sf -X POST "$API/v1/lab/assets" \
    -H "Content-Type: application/json" \
    -d '{"kind":"host","natural_key":"lab-debian"}' > /dev/null 2>&1 || true

# 3. Create identity_compromise incident for alice
info "Seeding auth events for alice@lab-debian..."
for i in $(seq 1 5); do
    curl -sf -X POST "$API/v1/events/raw" \
        -H "Content-Type: application/json" \
        -d "{\"source\":\"seeder\",\"kind\":\"auth.failed\",\"occurred_at\":\"2026-04-23T10:0${i}:00Z\",\"raw\":{},\"normalized\":{\"user\":\"alice\",\"source_ip\":\"1.2.3.4\",\"auth_type\":\"ssh\"},\"dedupe_key\":\"p11-fail-${i}\"}" \
        > /dev/null
done
curl -sf -X POST "$API/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"seeder","kind":"auth.succeeded","occurred_at":"2026-04-23T10:06:00Z","raw":{},"normalized":{"user":"alice","source_ip":"1.2.3.4","auth_type":"ssh"},"dedupe_key":"p11-success-1"}' \
    > /dev/null

INC_ID=$(curl -sf "$API/v1/incidents?limit=1" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'])")
info "Incident created: $INC_ID"

# 4. Propose + execute quarantine_host_lab
PROP=$(curl -sf -X POST "$API/v1/responses" \
    -H "Content-Type: application/json" \
    -d "{\"incident_id\":\"$INC_ID\",\"kind\":\"quarantine_host_lab\",\"params\":{\"host\":\"lab-debian\",\"source_ip\":\"1.2.3.4\"}}")
QACTION_ID=$(echo "$PROP" | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['id'])")

EXEC=$(curl -sf -X POST "$API/v1/responses/$QACTION_ID/execute")
Q_RESULT=$(echo "$EXEC" | python3 -c "import sys,json; print(json.load(sys.stdin)['log']['result'])")
Q_STATUS=$(echo "$EXEC" | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['status'])")
AR_STATUS=$(echo "$EXEC" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['log']['reversal_info']['ar_dispatch_status'])")

check "$Q_RESULT"  "ok"         "quarantine: action result ok"
check "$Q_STATUS"  "executed"   "quarantine: action status executed"
check "$AR_STATUS" "dispatched" "quarantine: AR dispatched"

# 5. Assert iptables DROP rule landed on lab-debian
info "Checking iptables rule on lab-debian..."
IPRULES=$($COMPOSE exec -T lab-debian iptables -S 2>/dev/null || echo "")
if echo "$IPRULES" | grep -q "DROP"; then
    ok "iptables DROP rule present on lab-debian"
else
    fail "iptables DROP rule NOT found on lab-debian"
fi

# 6. Start a long-running process in lab-debian for kill test
info "Starting sleep 120 on lab-debian..."
$COMPOSE exec -d lab-debian sleep 120
sleep 1
SLEEP_PID=$($COMPOSE exec -T lab-debian pgrep -n sleep 2>/dev/null || echo "")
[ -n "$SLEEP_PID" ] || { fail "Could not find sleep PID"; exit 1; }
info "sleep PID: $SLEEP_PID"

# 7. Propose + execute kill_process_lab
KPROP=$(curl -sf -X POST "$API/v1/responses" \
    -H "Content-Type: application/json" \
    -d "{\"incident_id\":\"$INC_ID\",\"kind\":\"kill_process_lab\",\"params\":{\"host\":\"lab-debian\",\"pid\":$SLEEP_PID,\"process_name\":\"sleep\"}}")
KACTION_ID=$(echo "$KPROP" | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['id'])")

KEXEC=$(curl -sf -X POST "$API/v1/responses/$KACTION_ID/execute")
K_RESULT=$(echo "$KEXEC" | python3 -c "import sys,json; print(json.load(sys.stdin)['log']['result'])")
check "$K_RESULT" "ok" "kill_process: action result ok"

# 8. Assert process is gone
sleep 2
if $COMPOSE exec -T lab-debian ps -p "$SLEEP_PID" > /dev/null 2>&1; then
    fail "Process $SLEEP_PID still running after kill"
else
    ok "Process $SLEEP_PID gone after kill"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Phase 11 smoke test — Results: PASS=$PASS FAIL=$FAIL"
exit $FAIL
