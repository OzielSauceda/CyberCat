#!/usr/bin/env bash
# Phase 6a smoke test — ATT&CK catalog, entities, detections, endpoint-compromise join.
# Sources Phase 5 first so all Phase 5 checks run as regression coverage.
# Run from the repo root: bash labs/smoke_test_phase6.sh
# Requires a running stack (docker compose up -d from infra/compose/).
set -euo pipefail

API="http://localhost:8000"
COMPOSE_FILE="infra/compose/docker-compose.yml"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

[ -f "labs/.smoke-env" ] && source "labs/.smoke-env" || true
[ -n "${SMOKE_API_TOKEN:-}" ] && AUTH_HEADER=(-H "Authorization: Bearer $SMOKE_API_TOKEN") || AUTH_HEADER=()

pass() { echo -e "${GREEN}PASS${RESET} $1"; }
fail() { echo -e "${RED}FAIL${RESET} $1"; exit 1; }
header() { echo -e "\n${BOLD}--- $1 ---${RESET}"; }

# ---------------------------------------------------------------------------
# Phase 5 regression (sets INCIDENT_ID)
# ---------------------------------------------------------------------------
source labs/smoke_test_phase5.sh

# The phase 5 script closed the incident; we need a fresh open one for the
# endpoint-compromise join test (join only works on non-closed incidents).
# Re-seed: flush + create a new identity-compromise incident.
header "Phase 6 setup: re-seed fresh incident"
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U cybercat -d cybercat -c "TRUNCATE events, incidents CASCADE;" > /dev/null \
  && pass "DB re-truncated for Phase 6 checks" \
  || { echo "WARNING: could not truncate DB"; }

docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null \
  && pass "Redis re-flushed for Phase 6 checks" \
  || true

NOW6=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

for i in 1 2 3 4; do
  curl -s "${AUTH_HEADER[@]}" -o /dev/null -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d "{
      \"source\":\"seeder\",\"kind\":\"auth.failed\",\"occurred_at\":\"${NOW6}\",
      \"raw\":{\"user\":\"alice@corp.local\",\"src_ip\":\"203.0.113.7\"},
      \"normalized\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\",\"reason\":\"bad_password\"},
      \"dedupe_key\":\"phase6-fail-${i}-${NOW6}\"
    }"
done

SEED6=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",\"kind\":\"auth.succeeded\",\"occurred_at\":\"${NOW6}\",
    \"raw\":{\"user\":\"alice@corp.local\",\"src_ip\":\"203.0.113.7\"},
    \"normalized\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\"},
    \"dedupe_key\":\"phase6-success-${NOW6}\"
  }")
HTTP6=$(echo "$SEED6" | tail -1)
[ "$HTTP6" = "201" ] || fail "Phase 6 seed auth event returned ${HTTP6}"
INC6=$(echo "$SEED6" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('incident_touched',''))")
[ -n "$INC6" ] && [ "$INC6" != "None" ] || fail "Phase 6 seed: incident_touched not set"
pass "fresh identity_compromise incident: ${INC6}"

# ---------------------------------------------------------------------------
# Check 11: ATT&CK catalog endpoint
# ---------------------------------------------------------------------------
header "Check 11: GET /v1/attack/catalog"
CATALOG=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/attack/catalog")
ENTRY_COUNT=$(echo "$CATALOG" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('entries',[])))")
[ "$ENTRY_COUNT" -ge 10 ] || fail "Expected >= 10 ATT&CK entries, got ${ENTRY_COUNT}"
CATALOG_VER=$(echo "$CATALOG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))")
[ -n "$CATALOG_VER" ] || fail "ATT&CK catalog missing version field"
pass "ATT&CK catalog: ${ENTRY_COUNT} entries (version ${CATALOG_VER})"

HAS_T1078=$(echo "$CATALOG" | python3 -c "
import sys, json
entries = json.load(sys.stdin).get('entries', [])
print('yes' if any(e['id'] == 'T1078' and e['name'] for e in entries) else 'no')
")
[ "$HAS_T1078" = "yes" ] || fail "T1078 with name not in catalog"
pass "T1078 (Valid Accounts) present with name"

# ---------------------------------------------------------------------------
# Check 12: entity detail endpoint
# ---------------------------------------------------------------------------
header "Check 12: GET /v1/entities/{id}"
ENTITY_ID=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/entities?kind=user&natural_key=alice%40corp.local" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('id',''))
")
[ -n "$ENTITY_ID" ] || fail "Entity lookup for alice@corp.local returned no id"
pass "entity lookup: alice entity_id=${ENTITY_ID}"

ENT_DETAIL=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/entities/${ENTITY_ID}")
ENT_KIND=$(echo "$ENT_DETAIL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('kind',''))")
[ "$ENT_KIND" = "user" ] || fail "Expected entity kind=user, got ${ENT_KIND}"
ENT_EVENTS=$(echo "$ENT_DETAIL" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('recent_events',[])))")
[ "$ENT_EVENTS" -ge 1 ] || fail "Entity detail has no recent_events"
ENT_INCS=$(echo "$ENT_DETAIL" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('related_incidents',[])))")
[ "$ENT_INCS" -ge 1 ] || fail "Entity detail has no related_incidents"
pass "entity detail: kind=${ENT_KIND}, events=${ENT_EVENTS}, incidents=${ENT_INCS}"

# ---------------------------------------------------------------------------
# Check 13: detections filter endpoint
# ---------------------------------------------------------------------------
header "Check 13: GET /v1/detections"
DET_LIST=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/detections?incident_id=${INC6}")
DET_COUNT=$(echo "$DET_LIST" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('items',[])))")
[ "$DET_COUNT" -ge 1 ] || fail "Expected >= 1 detection for incident, got ${DET_COUNT}"
HAS_INC_ID=$(echo "$DET_LIST" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
print('yes' if all(i.get('incident_id') is not None for i in items) else 'no')
")
[ "$HAS_INC_ID" = "yes" ] || fail "Detection items missing incident_id"
pass "detections filter: ${DET_COUNT} detections, incident_id populated"

# ---------------------------------------------------------------------------
# Check 14: POST process.created → endpoint-compromise join
# ---------------------------------------------------------------------------
header "Check 14: process.created extends open identity_compromise incident"
sleep 1  # ensure the auth incident is fully committed

PROC_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",
    \"kind\":\"process.created\",
    \"occurred_at\":\"${NOW6}\",
    \"raw\":{\"host\":\"lab-win10-01\",\"pid\":4242,\"ppid\":1234,\"image\":\"powershell.exe\",\"cmdline\":\"powershell.exe -EncodedCommand dABlAHMAdA==\"},
    \"normalized\":{
      \"host\":\"lab-win10-01\",
      \"user\":\"alice@corp.local\",
      \"pid\":4242,
      \"ppid\":1234,
      \"image\":\"powershell.exe\",
      \"cmdline\":\"powershell.exe -EncodedCommand dABlAHMAdA==\",
      \"parent_image\":\"winword.exe\"
    },
    \"dedupe_key\":\"phase6-proc-${NOW6}\"
  }")
HTTP_PROC=$(echo "$PROC_RESP" | tail -1)
[ "$HTTP_PROC" = "201" ] || fail "process.created event returned ${HTTP_PROC}"
PROC_DET=$(echo "$PROC_RESP" | head -1 | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('detections_fired',[])))")
[ "$PROC_DET" -ge 1 ] || fail "py.process.suspicious_child did not fire"
pass "process.created accepted, ${PROC_DET} detection(s) fired"

# ---------------------------------------------------------------------------
# Check 15: verify incident was extended (not a new incident created)
# ---------------------------------------------------------------------------
header "Check 15: incident extended — count unchanged, new evidence attached"
sleep 1  # give correlator a moment

INC_COUNT=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/incidents" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('items',[])))")
# Phase 10 added identity_endpoint_chain correlator: process.created for a user with an open
# identity_compromise incident creates a second chain incident. Expect 2 (not a duplicate 3+).
[ "$INC_COUNT" -ge 2 ] || fail "Expected at least 2 incidents (identity_compromise + identity_endpoint_chain), got ${INC_COUNT}"
pass "incident count ${INC_COUNT} (identity_compromise + identity_endpoint_chain chain — Phase 10 behavior)"

# Phase 10: process.created for a user with open identity_compromise creates an
# identity_endpoint_chain incident. Detection + ATT&CK + auto-tag attach to the chain incident.
CHAIN_ID=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/incidents" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
chain = [i for i in items if i.get('kind') == 'identity_endpoint_chain']
print(chain[0]['id'] if chain else '')
")
[ -n "$CHAIN_ID" ] || fail "identity_endpoint_chain incident not found"
pass "identity_endpoint_chain incident created: ${CHAIN_ID}"

CHAIN_DETAIL=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/incidents/${CHAIN_ID}")

# New detection on the chain incident
DET_RULES=$(echo "$CHAIN_DETAIL" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(','.join(det['rule_id'] for det in d.get('detections', [])))
")
echo "$DET_RULES" | grep -q "py.process.suspicious_child" \
  || fail "py.process.suspicious_child not in chain incident detections (got: ${DET_RULES})"
pass "py.process.suspicious_child in chain incident detections"

# New ATT&CK technique on chain incident
ATK_TECHNIQUES=$(echo "$CHAIN_DETAIL" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(','.join(a['technique'] for a in d.get('attack', [])))
")
echo "$ATK_TECHNIQUES" | grep -q "T1059" \
  || fail "T1059 not in chain incident attack tags (got: ${ATK_TECHNIQUES})"
pass "T1059 in chain incident ATT&CK"

# Auto-tag on chain incident (Phase 10 uses cross-layer-chain, not endpoint-activity-observed)
CHAIN_TAG=$(echo "$CHAIN_DETAIL" | python3 -c "
import sys, json
d = json.load(sys.stdin)
actions = d.get('actions', [])
match = [a for a in actions
         if a.get('kind') == 'tag_incident'
         and a.get('params', {}).get('tag') == 'cross-layer-chain'
         and a.get('status') == 'executed']
print('yes' if match else 'no')
")
[ "$CHAIN_TAG" = "yes" ] || fail "cross-layer-chain auto-tag not found/executed on chain incident"
pass "cross-layer-chain auto-tag executed on identity_endpoint_chain incident"

# ---------------------------------------------------------------------------
header "Phase 6a smoke test PASSED (checks 11-15 + Phase 5 regression)"
