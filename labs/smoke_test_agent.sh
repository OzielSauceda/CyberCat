#!/usr/bin/env bash
# Phase 16 smoke test — Custom Telemetry Agent (cct-agent)
# Run from the repo root: bash labs/smoke_test_agent.sh
#
# Prereq: ./start.sh (default profile = core+agent in Phase 16.6)
# Honours labs/.smoke-env for SMOKE_API_TOKEN if AUTH_REQUIRED=true.
#
# Verifies the full agent path end-to-end:
#   sshd auth failure inside lab-debian
#     → /var/log/auth.log
#     → cct-agent tail + parse
#     → POST /v1/events/raw (source=direct)
#     → backend ingest + detection + correlator
#     → identity_compromise incident
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
# 1. Backend + agent containers up
# ---------------------------------------------------------------------------
header "Containers"
http_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/healthz")
[ "$http_status" = "200" ] && pass "Backend /healthz returns 200" \
    || { fail "Backend not healthy (HTTP $http_status)"; exit 1; }

if docker ps --format "{{.Names}}" | grep -q "^compose-cct-agent-1$"; then
    pass "cct-agent container is running"
else
    fail "cct-agent container is not running — run ./start.sh first"
    exit 1
fi

if docker ps --format "{{.Names}}" | grep -q "^compose-lab-debian-1$"; then
    pass "lab-debian container is running"
else
    fail "lab-debian container is not running"
    exit 1
fi

# Wazuh containers must NOT be running by default (Phase 16.6 inversion)
if docker ps --format "{{.Names}}" | grep -qE "^compose-wazuh-(manager|indexer)-1$"; then
    warn "Wazuh containers are running — Phase 16 default is agent-only. (--profile wazuh active?)"
else
    pass "No Wazuh containers running (default profile is agent-only)"
fi

# ---------------------------------------------------------------------------
# 2. Agent reports it has started + tailing
# ---------------------------------------------------------------------------
header "Agent readiness"
if docker logs compose-cct-agent-1 2>&1 | grep -q "agent ready, tailing"; then
    pass "Agent log shows 'agent ready, tailing /lab/var/log/auth.log'"
else
    fail "Agent has not logged readiness; recent logs:"
    docker logs compose-cct-agent-1 --tail 20 2>&1
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Truncate DB + flush Redis for a clean assertion window
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
# 4. Trigger SSH failures + a final success inside lab-debian
# ---------------------------------------------------------------------------
header "Fire 5 SSH failures + 1 success inside lab-debian"
LAB_PASSWORD="${LAB_REALUSER_PASSWORD:-lab123}"
docker exec compose-lab-debian-1 bash -c "
  for i in 1 2 3 4 5; do
    sshpass -p wrong ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 realuser@localhost true 2>/dev/null
    sleep 0.3
  done
  # Successful auth from the same source after the burst — drives
  # py.auth.anomalous_source_success → identity_compromise incident.
  sshpass -p '$LAB_PASSWORD' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 realuser@localhost true 2>/dev/null || true
" || true
pass "5 SSH failures + 1 success triggered (realuser)"

# Wait for the agent to tail + parse + ship + backend to ingest + detector to fire
echo "Waiting 15s for end-to-end propagation..."
sleep 15

# ---------------------------------------------------------------------------
# 5. Assert events landed (source=direct, kind=auth.failed)
# ---------------------------------------------------------------------------
header "Events"
EV_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?source=direct&kind=auth.failed&limit=50") \
    || { fail "GET /v1/events failed"; exit 1; }
EV_COUNT=$(echo "$EV_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

if [ "$EV_COUNT" -ge 5 ]; then
    pass "Backend has $EV_COUNT direct auth.failed events (>=5)"
else
    fail "Expected >=5 direct auth.failed events, got $EV_COUNT"
    docker logs compose-cct-agent-1 --tail 30 2>&1
    exit 1
fi

# Spot-check shape on first item
SHAPE_OK=$(echo "$EV_RESP" | $PY -c '
import json, sys
items = json.load(sys.stdin)["items"]
e = items[0]
print("ok" if (e.get("source") == "direct" and e.get("kind") == "auth.failed") else "bad: " + str(e))
')
[ "$SHAPE_OK" = "ok" ] && pass "Event shape valid (source=direct, kind=auth.failed)" \
    || fail "Event shape invalid: $SHAPE_OK"

# ---------------------------------------------------------------------------
# 6. Assert detection fired (py.auth.failed_burst)
# ---------------------------------------------------------------------------
header "Detection"
DET_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/detections?rule_id=py.auth.failed_burst&limit=10") \
    || { fail "GET /v1/detections failed"; exit 1; }
DET_COUNT=$(echo "$DET_RESP" | $PY -c '
import json, sys
data = json.load(sys.stdin)
items = data.get("items", data) if isinstance(data, dict) else data
print(len(items))
')
if [ "$DET_COUNT" -ge 1 ]; then
    pass "py.auth.failed_burst fired ($DET_COUNT detection rows)"
else
    fail "py.auth.failed_burst did not fire"
    echo "DEBUG: detections response:"
    echo "$DET_RESP" | head -c 800
    exit 1
fi

# ---------------------------------------------------------------------------
# 7. Assert incident opened (identity_compromise)
# ---------------------------------------------------------------------------
header "Incident"
INC_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents?kind=identity_compromise&limit=10") \
    || { fail "GET /v1/incidents failed"; exit 1; }

INC_COUNT=$(echo "$INC_RESP" | $PY -c 'import json,sys; print(len(json.load(sys.stdin)["items"]))')
if [ "$INC_COUNT" -ge 1 ]; then
    pass "identity_compromise incident opened by agent-sourced events ($INC_COUNT)"
    echo "$INC_RESP" | $PY -c "
import json, sys
items = json.load(sys.stdin)['items']
for i in items[:3]:
    print('  - id={}... severity={} status={}'.format(i['id'][:8], i['severity'], i['status']))
" || true
else
    fail "Expected at least 1 identity_compromise incident, got 0"
    echo "DEBUG: all incidents:"
    curl -s "${AUTH_HEADER[@]}" "${API}/v1/incidents?limit=20" | $PY -m json.tool | head -40
fi

# ---------------------------------------------------------------------------
# 8. Assert agent's checkpoint advanced (durability check)
# ---------------------------------------------------------------------------
header "Checkpoint persistence"
CHECKPOINT_JSON=$(MSYS_NO_PATHCONV=1 docker exec compose-cct-agent-1 cat /var/lib/cct-agent/checkpoint.json 2>&1 || echo "MISSING")
if [ "$CHECKPOINT_JSON" = "MISSING" ] || ! echo "$CHECKPOINT_JSON" | grep -q "offset"; then
    fail "Checkpoint file missing or malformed: $CHECKPOINT_JSON"
else
    OFFSET=$(echo "$CHECKPOINT_JSON" | $PY -c 'import json,sys; print(json.load(sys.stdin)["offset"])')
    if [ "$OFFSET" -gt 0 ]; then
        pass "Checkpoint persisted at offset=$OFFSET"
    else
        fail "Checkpoint offset is 0 — agent has not advanced"
    fi
fi

# ---------------------------------------------------------------------------
# 9. Restart agent → verify dedup means no duplicate events
# ---------------------------------------------------------------------------
header "Restart agent — dedup invariant"
EV_BEFORE=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?source=direct&kind=auth.failed" \
    | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

docker compose -f "${COMPOSE_FILE}" restart cct-agent > /dev/null 2>&1
sleep 5

EV_AFTER=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?source=direct&kind=auth.failed" \
    | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

if [ "$EV_BEFORE" = "$EV_AFTER" ]; then
    pass "Restart did not duplicate events (count stayed at $EV_AFTER)"
else
    fail "Restart created duplicates (was $EV_BEFORE, now $EV_AFTER)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Phase 16 smoke test complete: ${GREEN}${PASSES} passed${RESET}, ${RED}${FAILURES} failed${RESET}"
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1
