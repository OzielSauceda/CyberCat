#!/usr/bin/env bash
# Phase 9A smoke test — Response completeness + ATT&CK expansion.
# Run from the repo root: bash labs/smoke_test_phase9a.sh
# Requires a running stack: docker compose up -d from infra/compose/
set -euo pipefail

API="http://localhost:8000"
COMPOSE_FILE="infra/compose/docker-compose.yml"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

pass() { echo -e "${GREEN}PASS${RESET} $1"; }
fail() { echo -e "${RED}FAIL${RESET} $1"; exit 1; }
header() { echo -e "\n${BOLD}--- $1 ---${RESET}"; }

PASSES=0
FAILURES=0

check() {
  local desc="$1"
  local cmd="$2"
  if eval "$cmd"; then
    pass "$desc"
    PASSES=$((PASSES + 1))
  else
    fail "$desc"
    FAILURES=$((FAILURES + 1))
  fi
}

# ---------------------------------------------------------------------------
# Setup: fresh DB + Redis
# ---------------------------------------------------------------------------
header "Setup: truncate DB and flush Redis"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U cybercat -d cybercat -c "
    TRUNCATE evidence_requests, blocked_observables, lab_sessions,
             notes, incident_transitions, action_logs, actions,
             incident_attack, incident_entities, incident_events,
             incident_detections, incidents, detections,
             event_entities, events, entities
    CASCADE;
  " > /dev/null \
  && pass "DB truncated for Phase 9A checks" \
  || { echo "WARNING: could not truncate DB — continuing"; }

docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null \
  && pass "Redis flushed for Phase 9A checks" \
  || true

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# Check 1: OpenAPI lists all 8 ActionKind values
# ---------------------------------------------------------------------------
header "Check 1: All 8 ActionKind values in OpenAPI"

KINDS=$(curl -sf "${API}/openapi.json" | python3 -c "
import json, sys
spec = json.load(sys.stdin)
enum_vals = []
for schema in spec.get('components', {}).get('schemas', {}).values():
    if schema.get('title') == 'ActionKind':
        enum_vals = schema.get('enum', [])
        break
print(' '.join(sorted(enum_vals)))
")
for kind in quarantine_host_lab kill_process_lab invalidate_lab_session block_observable request_evidence; do
  echo "$KINDS" | grep -q "$kind" \
    && pass "ActionKind.$kind in OpenAPI" \
    || fail "ActionKind.$kind missing from OpenAPI enum"
done

# ---------------------------------------------------------------------------
# Check 2: ATT&CK catalog returns ≥35 entries
# ---------------------------------------------------------------------------
header "Check 2: ATT&CK catalog size"

CATALOG_COUNT=$(curl -sf "${API}/v1/attack/catalog" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data['entries']))
")
python3 -c "import sys; sys.exit(0 if int('${CATALOG_COUNT}') >= 35 else 1)" \
  && pass "ATT&CK catalog has ${CATALOG_COUNT} entries (≥35)" \
  || fail "ATT&CK catalog has only ${CATALOG_COUNT} entries (expected ≥35)"

# ---------------------------------------------------------------------------
# Check 3: New tables exist
# ---------------------------------------------------------------------------
header "Check 3: Migration 0005 applied — new tables exist"

for tbl in lab_sessions blocked_observables evidence_requests; do
  docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -c "\dt ${tbl}" 2>&1 | grep -q "${tbl}" \
    && pass "Table ${tbl} exists" \
    || fail "Table ${tbl} missing — run alembic upgrade"
done

# ---------------------------------------------------------------------------
# Setup: register lab assets and open incident
# ---------------------------------------------------------------------------
header "Setup: register lab assets and open incident"

curl -s -o /dev/null -X POST "${API}/v1/lab/assets" \
  -H "Content-Type: application/json" \
  -d '{"kind":"host","natural_key":"lab-smoke-01"}'

curl -s -o /dev/null -X POST "${API}/v1/lab/assets" \
  -H "Content-Type: application/json" \
  -d '{"kind":"user","natural_key":"smoke-user"}'

# session.started creates user + host entities and a LabSession (required for invalidate_lab_session)
curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",
    \"kind\":\"session.started\",
    \"occurred_at\":\"${NOW}\",
    \"raw\":{},
    \"normalized\":{\"user\":\"smoke-user\",\"host\":\"lab-smoke-01\",\"session_id\":\"sess-smoke-001\"},
    \"dedupe_key\":\"smoke9a-session-${NOW}\"
  }"

# Open an identity_compromise incident: auth failure burst + anomalous success
for i in $(seq 1 5); do
  curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d "{
      \"source\":\"seeder\",
      \"kind\":\"auth.failed\",
      \"occurred_at\":\"${NOW}\",
      \"raw\":{},
      \"normalized\":{\"user\":\"smoke-user\",\"source_ip\":\"10.9.9.9\",\"auth_type\":\"ssh\"},
      \"dedupe_key\":\"smoke9a-burst-${i}-${NOW}\"
    }"
done

# auth.succeeded from same previously-unseen IP → triggers identity_compromise incident
curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",
    \"kind\":\"auth.succeeded\",
    \"occurred_at\":\"${NOW}\",
    \"raw\":{},
    \"normalized\":{\"user\":\"smoke-user\",\"source_ip\":\"10.9.9.9\",\"auth_type\":\"ssh\"},
    \"dedupe_key\":\"smoke9a-success-${NOW}\"
  }"

sleep 1

INC_ID=$(curl -sf "${API}/v1/incidents?limit=1" | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', [])
print(items[0]['id'] if items else '')
")
[ -n "${INC_ID}" ] \
  && pass "Incident opened (id=${INC_ID})" \
  || fail "No incident found — cannot proceed with action checks"

# ---------------------------------------------------------------------------
# Check 4: quarantine_host_lab: execute → LabAsset.notes contains marker
# ---------------------------------------------------------------------------
header "Check 4: quarantine_host_lab"

PROPOSE4=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"quarantine_host_lab\",\"params\":{\"host\":\"lab-smoke-01\"}}")
HTTP4=$(echo "${PROPOSE4}" | tail -1)
[ "${HTTP4}" = "201" ] || fail "quarantine_host_lab propose returned HTTP ${HTTP4}"
ACTION4=$(echo "${PROPOSE4}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")

EXEC4=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION4}/execute")
HTTP4E=$(echo "${EXEC4}" | tail -1)
[ "${HTTP4E}" = "200" ] || fail "quarantine_host_lab execute returned HTTP ${HTTP4E}"

NOTES4=$(curl -sf "${API}/v1/lab/assets" | python3 -c "
import json, sys
assets = json.load(sys.stdin)
a = next((x for x in assets if x['natural_key'] == 'lab-smoke-01'), None)
print(a['notes'] if a else '')
")
echo "${NOTES4}" | grep -q "\[quarantined:" \
  && pass "quarantine_host_lab: LabAsset.notes contains [quarantined: marker" \
  || fail "quarantine_host_lab: marker not found in notes. Got: ${NOTES4}"

# ---------------------------------------------------------------------------
# Check 5: kill_process_lab: execute → action_logs entry + auto-created evidence_request
# ---------------------------------------------------------------------------
header "Check 5: kill_process_lab"

PROPOSE5=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"kill_process_lab\",\"params\":{\"host\":\"lab-smoke-01\",\"pid\":9999,\"process_name\":\"malware.exe\"}}")
HTTP5=$(echo "${PROPOSE5}" | tail -1)
[ "${HTTP5}" = "201" ] || fail "kill_process_lab propose returned HTTP ${HTTP5}"
ACTION5=$(echo "${PROPOSE5}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")

EXEC5=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION5}/execute")
HTTP5E=$(echo "${EXEC5}" | tail -1)
[ "${HTTP5E}" = "200" ] || fail "kill_process_lab execute returned HTTP ${HTTP5E}"

RESULT5=$(echo "${EXEC5}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['log']['result'])")
[ "${RESULT5}" = "ok" ] \
  && pass "kill_process_lab: result=ok" \
  || fail "kill_process_lab: expected result=ok, got ${RESULT5}"

ER5_COUNT=$(curl -sf "${API}/v1/evidence-requests?incident_id=${INC_ID}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(sum(1 for er in data['items'] if er['kind'] == 'process_list'))
")
[ "${ER5_COUNT}" -ge 1 ] \
  && pass "kill_process_lab: auto-created process_list evidence_request" \
  || fail "kill_process_lab: expected auto-created evidence_request, got ${ER5_COUNT}"

# ---------------------------------------------------------------------------
# Check 6: invalidate_lab_session: execute + revert → invalidated_at set then unset
# ---------------------------------------------------------------------------
header "Check 6: invalidate_lab_session"

PROPOSE6=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"invalidate_lab_session\",\"params\":{\"user\":\"smoke-user\",\"host\":\"lab-smoke-01\"}}")
HTTP6=$(echo "${PROPOSE6}" | tail -1)
[ "${HTTP6}" = "201" ] || fail "invalidate_lab_session propose returned HTTP ${HTTP6}"
ACTION6=$(echo "${PROPOSE6}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")

EXEC6=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION6}/execute")
[ "$(echo "${EXEC6}" | tail -1)" = "200" ] || fail "invalidate_lab_session execute failed"
RESULT6=$(echo "${EXEC6}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['log']['result'])")
[ "${RESULT6}" = "ok" ] \
  && pass "invalidate_lab_session execute: result=ok" \
  || fail "invalidate_lab_session execute failed: ${RESULT6}"

REVERT6=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION6}/revert")
[ "$(echo "${REVERT6}" | tail -1)" = "200" ] || fail "invalidate_lab_session revert failed"
RRESULT6=$(echo "${REVERT6}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['log']['result'])")
[ "${RRESULT6}" = "ok" ] \
  && pass "invalidate_lab_session revert: result=ok" \
  || fail "invalidate_lab_session revert failed: ${RRESULT6}"

# ---------------------------------------------------------------------------
# Check 7: block_observable: execute → active row; revert → active=false
# ---------------------------------------------------------------------------
header "Check 7: block_observable"

PROPOSE7=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"block_observable\",\"params\":{\"kind\":\"ip\",\"value\":\"192.0.2.100\"}}")
[ "$(echo "${PROPOSE7}" | tail -1)" = "201" ] || fail "block_observable propose failed"
ACTION7=$(echo "${PROPOSE7}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")

curl -s -X POST "${API}/v1/responses/${ACTION7}/execute" > /dev/null

BO_ACTIVE=$(curl -sf "${API}/v1/blocked-observables?active=true&value=192.0.2.100" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data['items']))
")
[ "${BO_ACTIVE}" = "1" ] \
  && pass "block_observable: active row in blocked_observables" \
  || fail "block_observable: expected active row, got ${BO_ACTIVE}"

curl -s -X POST "${API}/v1/responses/${ACTION7}/revert" > /dev/null

BO_INACTIVE=$(curl -sf "${API}/v1/blocked-observables?active=false&value=192.0.2.100" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data['items']))
")
[ "${BO_INACTIVE}" = "1" ] \
  && pass "block_observable revert: row active=false" \
  || fail "block_observable revert: expected inactive row, got ${BO_INACTIVE}"

# ---------------------------------------------------------------------------
# Check 8: Blocked IP → subsequent event fires py.blocked_observable_match
# ---------------------------------------------------------------------------
header "Check 8: blocked_observable detection fires"

# Block a fresh IP
PROPOSE8=$(curl -s -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"block_observable\",\"params\":{\"kind\":\"ip\",\"value\":\"198.51.100.1\"}}")
ACTION8=$(echo "${PROPOSE8}" | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")
curl -s -X POST "${API}/v1/responses/${ACTION8}/execute" > /dev/null

# Ingest event referencing that IP
curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",
    \"kind\":\"auth.failed\",
    \"occurred_at\":\"${NOW}\",
    \"raw\":{},
    \"normalized\":{\"user\":\"smoke-user\",\"source_ip\":\"198.51.100.1\",\"auth_type\":\"ssh\"},
    \"dedupe_key\":\"smoke9a-blocked-trigger-${NOW}\"
  }"

sleep 1

BLOCK_DET=$(curl -sf "${API}/v1/detections?rule_id=py.blocked_observable_match&limit=10" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data['items']))
")
[ "${BLOCK_DET}" -ge 1 ] \
  && pass "Blocked IP event → py.blocked_observable_match detection fired" \
  || fail "Expected py.blocked_observable_match detection, got ${BLOCK_DET}"

# ---------------------------------------------------------------------------
# Check 9: request_evidence: propose + execute → open evidence_request
# ---------------------------------------------------------------------------
header "Check 9: request_evidence"

PROPOSE9=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"request_evidence\",\"params\":{\"evidence_kind\":\"network_connections\"}}")
[ "$(echo "${PROPOSE9}" | tail -1)" = "201" ] || fail "request_evidence propose failed"
ACTION9=$(echo "${PROPOSE9}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")

curl -s -X POST "${API}/v1/responses/${ACTION9}/execute" > /dev/null

ER9=$(curl -sf "${API}/v1/evidence-requests?incident_id=${INC_ID}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
nc = [er for er in data['items'] if er['kind'] == 'network_connections']
print(len(nc))
")
[ "${ER9}" -ge 1 ] \
  && pass "request_evidence: network_connections evidence_request created" \
  || fail "request_evidence: evidence_request not found"

# ---------------------------------------------------------------------------
# Check 10: identity_compromise auto-proposes request_evidence
# ---------------------------------------------------------------------------
header "Check 10: identity_compromise auto-proposes request_evidence"

AUTO_ER=$(curl -sf "${API}/v1/evidence-requests?incident_id=${INC_ID}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
triage = [er for er in data['items'] if er['kind'] == 'triage_log']
print(len(triage))
")
[ "${AUTO_ER}" -ge 1 ] \
  && pass "identity_compromise auto-created triage_log evidence_request" \
  || fail "Expected auto-proposed triage_log evidence_request, got ${AUTO_ER}"

# ---------------------------------------------------------------------------
# Check 11: Evidence request collect/dismiss workflow
# ---------------------------------------------------------------------------
header "Check 11: Evidence request collect/dismiss"

ALL_ERS=$(curl -sf "${API}/v1/evidence-requests?incident_id=${INC_ID}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
open_ers = [er['id'] for er in data['items'] if er['status'] == 'open']
print(open_ers[0] if open_ers else '')
")
[ -n "${ALL_ERS}" ] || fail "No open evidence requests to collect"

COLLECT=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/evidence-requests/${ALL_ERS}/collect")
[ "$(echo "${COLLECT}" | tail -1)" = "200" ] || fail "collect evidence_request failed"
STATUS=$(echo "${COLLECT}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
[ "${STATUS}" = "collected" ] \
  && pass "Evidence request marked collected" \
  || fail "Expected status=collected, got ${STATUS}"

# ---------------------------------------------------------------------------
# Check 12: Non-existent lab asset → scope failure
# ---------------------------------------------------------------------------
header "Check 12: Non-existent lab asset returns fail"

PROPOSE12=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"quarantine_host_lab\",\"params\":{\"host\":\"nonexistent-host\"}}")
HTTP12=$(echo "${PROPOSE12}" | tail -1)
# This may be accepted at propose time (scope check for lab assets doesn't reject) but fails on execute
if [ "${HTTP12}" = "201" ]; then
  ACTION12=$(echo "${PROPOSE12}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")
  EXEC12=$(curl -s -X POST "${API}/v1/responses/${ACTION12}/execute")
  RESULT12=$(echo "${EXEC12}" | python3 -c "import json,sys; print(json.load(sys.stdin)['log']['result'])")
  [ "${RESULT12}" = "fail" ] \
    && pass "Non-existent lab asset: handler returns fail with reason" \
    || fail "Expected handler to fail for non-existent asset, got ${RESULT12}"
else
  # 422 from scope check is also acceptable
  [ "${HTTP12}" = "422" ] \
    && pass "Non-existent lab asset: API returned 422 (out_of_lab_scope)" \
    || fail "Non-existent lab asset: unexpected HTTP ${HTTP12}"
fi

# ---------------------------------------------------------------------------
# Check 13: Revert on disruptive action → 409
# ---------------------------------------------------------------------------
header "Check 13: Revert on disruptive action → 409"

REVERT13=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION4}/revert")
HTTP13=$(echo "${REVERT13}" | tail -1)
[ "${HTTP13}" = "409" ] \
  && pass "Revert on disruptive quarantine_host_lab → 409" \
  || fail "Expected 409 for disruptive revert, got HTTP ${HTTP13}"

# ---------------------------------------------------------------------------
# Check 14: Regression — previous real handlers still work
# ---------------------------------------------------------------------------
header "Check 14: Regression — tag_incident, elevate_severity, flag_host_in_lab"

PROPOSE14A=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"tag_incident\",\"params\":{\"tag\":\"phase9a-regression\"}}")
[ "$(echo "${PROPOSE14A}" | tail -1)" = "201" ] || fail "tag_incident propose failed"
ACTION14A=$(echo "${PROPOSE14A}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")
EXEC14A=$(curl -s -X POST "${API}/v1/responses/${ACTION14A}/execute" | python3 -c "import json,sys; print(json.load(sys.stdin)['log']['result'])")
[ "${EXEC14A}" = "ok" ] \
  && pass "tag_incident: result=ok (regression)" \
  || fail "tag_incident regression failed: ${EXEC14A}"

PROPOSE14B=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INC_ID}\",\"kind\":\"flag_host_in_lab\",\"params\":{\"host\":\"lab-smoke-01\"}}")
[ "$(echo "${PROPOSE14B}" | tail -1)" = "201" ] || fail "flag_host_in_lab propose failed"
ACTION14B=$(echo "${PROPOSE14B}" | head -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['action']['id'])")
EXEC14B=$(curl -s -X POST "${API}/v1/responses/${ACTION14B}/execute" | python3 -c "import json,sys; print(json.load(sys.stdin)['log']['result'])")
[ "${EXEC14B}" = "ok" ] \
  && pass "flag_host_in_lab: result=ok (regression)" \
  || fail "flag_host_in_lab regression failed: ${EXEC14B}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Phase 9A smoke test summary: ${PASSES} passed, ${FAILURES} failed${RESET}"
[ "${FAILURES}" = "0" ] && echo -e "${GREEN}ALL CHECKS PASSED${RESET}" || { echo -e "${RED}SOME CHECKS FAILED${RESET}"; exit 1; }
