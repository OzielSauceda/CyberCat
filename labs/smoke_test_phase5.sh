#!/usr/bin/env bash
# Phase 5a smoke test — transitions, notes, propose/execute/revert, scope rejection.
# Run from the repo root: bash labs/smoke_test_phase5.sh
# Requires a running stack (docker compose up -d from infra/compose/).
# Flushes Redis at startup so it is safe to run after Phase 3 without a volume wipe.
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
# Pre-flight: wipe events/incidents/lab state from DB and flush Redis
# Explicitly registers required lab assets so this test is self-contained
# and does not depend on migration 0003 seeds persisting.
# ---------------------------------------------------------------------------
header "Pre-flight: reset DB and Redis"
docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U cybercat -d cybercat \
  -c "TRUNCATE lab_sessions, lab_assets CASCADE; TRUNCATE events, incidents CASCADE;" > /dev/null \
  && pass "DB truncated (lab_assets + events + incidents cascade)" \
  || { echo "WARNING: could not truncate DB — results may be affected by prior runs"; }

docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null \
  && pass "Redis flushed" \
  || { echo "WARNING: could not flush Redis — results may be affected by prior runs"; }

# Register standard lab host — required for Step 5 flag_host_in_lab scope check
LAB_REG=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/lab/assets" \
  -H "Content-Type: application/json" \
  -d '{"kind":"host","natural_key":"lab-win10-01"}')
[ "$LAB_REG" = "201" ] || [ "$LAB_REG" = "409" ] \
  && pass "lab-win10-01 registered (${LAB_REG})" \
  || fail "Could not register lab-win10-01, got ${LAB_REG}"

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# Step 1: seed the incident (Phase 3 events)
# ---------------------------------------------------------------------------
header "Step 1: seed incident"
for i in 1 2 3 4; do
  curl -s "${AUTH_HEADER[@]}" -o /dev/null -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d "{
      \"source\":\"seeder\",\"kind\":\"auth.failed\",\"occurred_at\":\"${NOW}\",
      \"raw\":{\"user\":\"alice@corp.local\",\"src_ip\":\"203.0.113.7\"},
      \"normalized\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\",\"reason\":\"bad_password\"},
      \"dedupe_key\":\"phase5-fail-${i}-${NOW}\"
    }"
done

SEED_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",\"kind\":\"auth.succeeded\",\"occurred_at\":\"${NOW}\",
    \"raw\":{\"user\":\"alice@corp.local\",\"src_ip\":\"203.0.113.7\"},
    \"normalized\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\"},
    \"dedupe_key\":\"phase5-success-${NOW}\"
  }")
HTTP=$(echo "$SEED_RESP" | tail -1)
[ "$HTTP" = "201" ] || fail "Seed event returned ${HTTP}"

INCIDENT_TOUCHED=$(echo "$SEED_RESP" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('incident_touched',''))")
[ -n "$INCIDENT_TOUCHED" ] && [ "$INCIDENT_TOUCHED" != "None" ] || fail "incident_touched not set after auth.succeeded"
INCIDENT_ID="$INCIDENT_TOUCHED"
pass "incident created: ${INCIDENT_ID}"

# ---------------------------------------------------------------------------
# Step 2: auto-actions executed by system:correlator
# ---------------------------------------------------------------------------
header "Step 2: auto-actions (system:correlator)"
sleep 1  # give the post-commit hook a moment to commit
AUTO_ACTIONS=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/responses?incident_id=${INCIDENT_ID}")
AUTO_COUNT=$(echo "$AUTO_ACTIONS" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
print(len([i for i in items if i['proposed_by'] == 'system' and i['status'] == 'executed']))
")
[ "$AUTO_COUNT" -ge 2 ] || fail "Expected >= 2 auto-executed system actions, got ${AUTO_COUNT}"
pass "${AUTO_COUNT} system actions auto-executed"

REASON_COUNT=$(echo "$AUTO_ACTIONS" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
print(len([i for i in items if i.get('classification_reason')]))
")
[ "$REASON_COUNT" -ge 1 ] || fail "classification_reason not populated"
pass "classification_reason populated on actions"

# ---------------------------------------------------------------------------
# Step 3: add a note
# ---------------------------------------------------------------------------
header "Step 3: add note"
NOTE_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/notes" \
  -H "Content-Type: application/json" \
  -d '{"body":"Alice confirmed she did not travel to this IP region. Escalating."}')
HTTP=$(echo "$NOTE_RESP" | tail -1)
[ "$HTTP" = "201" ] || fail "Expected 201 for note creation, got ${HTTP}"
NOTE_ID=$(echo "$NOTE_RESP" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
pass "note created: ${NOTE_ID}"

NOTE_IN_DETAIL=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/incidents/${INCIDENT_ID}" | python3 -c "
import sys, json
print(len(json.load(sys.stdin).get('notes', [])))
")
[ "$NOTE_IN_DETAIL" -ge 1 ] || fail "Note not visible in incident detail"
pass "note visible in detail"

# ---------------------------------------------------------------------------
# Step 4: empty body should 422
# ---------------------------------------------------------------------------
header "Step 4: empty note body → 422"
HTTP_EMPTY=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/notes" \
  -H "Content-Type: application/json" \
  -d '{"body":"   "}')
[ "$HTTP_EMPTY" = "422" ] || fail "Expected 422 for empty body, got ${HTTP_EMPTY}"
pass "422 for empty note body (correct)"

# ---------------------------------------------------------------------------
# Step 5: propose + execute flag_host_in_lab
# ---------------------------------------------------------------------------
header "Step 5: propose + execute flag_host_in_lab"
PROPOSE_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INCIDENT_ID}\",\"kind\":\"flag_host_in_lab\",\"params\":{\"host\":\"lab-win10-01\"}}")
HTTP=$(echo "$PROPOSE_RESP" | tail -1)
[ "$HTTP" = "201" ] || fail "Expected 201 for propose, got ${HTTP}"
ACTION_ID=$(echo "$PROPOSE_RESP" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['id'])")
CLASSIF=$(echo "$PROPOSE_RESP" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['classification'])")
[ "$CLASSIF" = "reversible" ] || fail "Expected classification=reversible, got ${CLASSIF}"
pass "action proposed: ${ACTION_ID} (classification=reversible)"

EXEC_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION_ID}/execute")
HTTP=$(echo "$EXEC_RESP" | tail -1)
[ "$HTTP" = "200" ] || fail "Expected 200 for execute, got ${HTTP}"
STATUS=$(echo "$EXEC_RESP" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['status'])")
[ "$STATUS" = "executed" ] || fail "Expected status=executed, got ${STATUS}"
pass "action executed"

# ---------------------------------------------------------------------------
# Step 6: revert flag_host_in_lab
# ---------------------------------------------------------------------------
header "Step 6: revert flag_host_in_lab"
REVERT_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n%{http_code}" -X POST "${API}/v1/responses/${ACTION_ID}/revert")
HTTP=$(echo "$REVERT_RESP" | tail -1)
[ "$HTTP" = "200" ] || fail "Expected 200 for revert, got ${HTTP}"
STATUS=$(echo "$REVERT_RESP" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin)['action']['status'])")
[ "$STATUS" = "reverted" ] || fail "Expected status=reverted, got ${STATUS}"
pass "action reverted"

# Verify original log row still exists (audit intact)
LOGS=$(curl -s "${AUTH_HEADER[@]}" "${API}/v1/responses?incident_id=${INCIDENT_ID}" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
# last_log on the reverted action should reflect the revert
match = [i for i in items if i['id'] == '${ACTION_ID}']
print(match[0]['last_log']['result'] if match else 'not_found')
")
[ "$LOGS" = "ok" ] || fail "Expected last_log.result=ok after revert, got ${LOGS}"
pass "last_log.result=ok after revert"

# ---------------------------------------------------------------------------
# Step 7: out-of-lab-scope rejection
# ---------------------------------------------------------------------------
header "Step 7: out-of-lab-scope rejection"
HTTP_SCOPE=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/responses" \
  -H "Content-Type: application/json" \
  -d "{\"incident_id\":\"${INCIDENT_ID}\",\"kind\":\"flag_host_in_lab\",\"params\":{\"host\":\"not-a-lab-host\"}}")
[ "$HTTP_SCOPE" = "422" ] || fail "Expected 422 for out-of-scope host, got ${HTTP_SCOPE}"
pass "422 for out-of-scope host (correct)"

# ---------------------------------------------------------------------------
# Step 8: transitions
# ---------------------------------------------------------------------------
header "Step 8: transitions"
HTTP_T=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/transitions" \
  -H "Content-Type: application/json" -d '{"to_status":"triaged"}')
[ "$HTTP_T" = "201" ] || fail "new→triaged returned ${HTTP_T}"
pass "new → triaged"

HTTP_T=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/transitions" \
  -H "Content-Type: application/json" -d '{"to_status":"investigating"}')
[ "$HTTP_T" = "201" ] || fail "triaged→investigating returned ${HTTP_T}"
pass "triaged → investigating"

# contained requires reason — 422 without it
HTTP_NO_REASON=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/transitions" \
  -H "Content-Type: application/json" -d '{"to_status":"contained"}')
[ "$HTTP_NO_REASON" = "422" ] || fail "Expected 422 for missing reason, got ${HTTP_NO_REASON}"
pass "422 for missing reason on contained (correct)"

HTTP_T=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/transitions" \
  -H "Content-Type: application/json" \
  -d '{"to_status":"contained","reason":"Blocked source IP at perimeter firewall."}')
[ "$HTTP_T" = "201" ] || fail "investigating→contained returned ${HTTP_T}"
pass "investigating → contained (with reason)"

HTTP_T=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/transitions" \
  -H "Content-Type: application/json" \
  -d '{"to_status":"closed","reason":"Confirmed and remediated."}')
[ "$HTTP_T" = "201" ] || fail "contained→closed returned ${HTTP_T}"
pass "contained → closed"

# invalid transition: closed → investigating should 409
HTTP_INVALID=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" -X POST "${API}/v1/incidents/${INCIDENT_ID}/transitions" \
  -H "Content-Type: application/json" -d '{"to_status":"investigating"}')
[ "$HTTP_INVALID" = "409" ] || fail "Expected 409 for closed→investigating, got ${HTTP_INVALID}"
pass "409 on closed→investigating (correct)"

# ---------------------------------------------------------------------------
header "Phase 5a smoke test PASSED"
