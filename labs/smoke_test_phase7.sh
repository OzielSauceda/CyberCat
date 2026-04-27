#!/usr/bin/env bash
# Phase 7 smoke test — Sigma detections, standalone endpoint correlator, /actions dashboard.
# Sources Phase 6 first so all Phase 6 checks run as regression coverage.
# Run from the repo root: bash labs/smoke_test_phase7.sh
# Requires a running stack (docker compose up -d from infra/compose/).
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

# ---------------------------------------------------------------------------
# Phase 6 regression
# ---------------------------------------------------------------------------
source labs/smoke_test_phase6.sh

# ---------------------------------------------------------------------------
# Phase 7 setup: fresh DB + Redis
# ---------------------------------------------------------------------------
header "Phase 7 setup: truncate DB and flush Redis"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U cybercat -d cybercat -c "TRUNCATE events, incidents CASCADE;" > /dev/null \
  && pass "DB truncated for Phase 7 checks" \
  || { echo "WARNING: could not truncate DB — continuing"; }

docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null \
  && pass "Redis flushed for Phase 7 checks" \
  || true

NOW7=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# Check 16: OpenAPI spec is live and has correct title
# ---------------------------------------------------------------------------
header "Check 16: OpenAPI spec title"
SPEC_TITLE=$(curl -sf "${API}/openapi.json" | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['title'])")
[ "${SPEC_TITLE}" = "CyberCat" ] \
  && pass "OpenAPI spec title == 'CyberCat'" \
  || fail "OpenAPI spec title is '${SPEC_TITLE}', expected 'CyberCat'"

# ---------------------------------------------------------------------------
# Check 17: Standalone endpoint correlator — fresh process event opens medium incident
# ---------------------------------------------------------------------------
header "Check 17: Standalone endpoint incident (no prior identity event)"

PROC17=$(curl -s -w "\n%{http_code}" -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",
    \"kind\":\"process.created\",
    \"occurred_at\":\"${NOW7}\",
    \"raw\":{\"host\":\"lab-win10-01\",\"pid\":1234,\"ppid\":456,\"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",\"cmdline\":\"powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\"},
    \"normalized\":{
      \"host\":\"lab-win10-01\",
      \"pid\":1234,\"ppid\":456,
      \"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",
      \"cmdline\":\"powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\"
    },
    \"dedupe_key\":\"phase7-standalone-001-${NOW7}\"
  }")

HTTP17=$(echo "${PROC17}" | tail -1)
[ "${HTTP17}" = "201" ] || fail "Process event ingestion returned HTTP ${HTTP17}"

sleep 1

INCIDENTS17=$(curl -sf "${API}/v1/incidents?limit=10")
EC_COUNT=$(echo "${INCIDENTS17}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print(sum(1 for i in data['items'] if i['kind']=='endpoint_compromise'))
")
[ "${EC_COUNT}" = "1" ] \
  && pass "One endpoint_compromise incident opened" \
  || fail "Expected 1 endpoint_compromise incident, got ${EC_COUNT}"

EC_SEV=$(echo "${INCIDENTS17}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
items=[i for i in data['items'] if i['kind']=='endpoint_compromise']
print(items[0]['severity'] if items else 'none')
")
[ "${EC_SEV}" = "medium" ] \
  && pass "Standalone endpoint incident severity == medium" \
  || fail "Expected severity 'medium', got '${EC_SEV}'"

EC_CONF=$(echo "${INCIDENTS17}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
items=[i for i in data['items'] if i['kind']=='endpoint_compromise']
print(items[0]['confidence'] if items else '0')
")
python3 -c "import sys; c=float('${EC_CONF}'); sys.exit(0 if abs(c-0.60)<0.01 else 1)" \
  && pass "Standalone endpoint incident confidence == 0.60" \
  || fail "Expected confidence 0.60, got ${EC_CONF}"

# ---------------------------------------------------------------------------
# Check 18: Dedup — re-posting same host in same hour does not open second incident
# ---------------------------------------------------------------------------
header "Check 18: Standalone endpoint dedup"

curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",
    \"kind\":\"process.created\",
    \"occurred_at\":\"${NOW7}\",
    \"raw\":{\"host\":\"lab-win10-01\",\"pid\":9999,\"ppid\":456,\"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",\"cmdline\":\"powershell.exe -enc ZGlmZmVyZW50\"},
    \"normalized\":{
      \"host\":\"lab-win10-01\",
      \"pid\":9999,\"ppid\":456,
      \"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",
      \"cmdline\":\"powershell.exe -enc ZGlmZmVyZW50\"
    },
    \"dedupe_key\":\"phase7-standalone-002-${NOW7}\"
  }"

sleep 1

EC_COUNT2=$(curl -sf "${API}/v1/incidents?limit=10" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print(sum(1 for i in data['items'] if i['kind']=='endpoint_compromise'))
")
[ "${EC_COUNT2}" = "1" ] \
  && pass "Dedup holds — still 1 endpoint_compromise incident after second event" \
  || fail "Dedup failed — expected 1 incident, got ${EC_COUNT2}"

# ---------------------------------------------------------------------------
# Check 19: Join wins — identity chain followed by process event → identity_compromise, no standalone
# ---------------------------------------------------------------------------
header "Check 19: Join correlator takes precedence over standalone"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U cybercat -d cybercat -c "TRUNCATE events, incidents CASCADE;" > /dev/null 2>&1 || true
docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null || true

NOW19=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

for i in 1 2 3 4; do
  curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d "{
      \"source\":\"seeder\",\"kind\":\"auth.failed\",\"occurred_at\":\"${NOW19}\",
      \"raw\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\"},
      \"normalized\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\"},
      \"dedupe_key\":\"phase7-join-fail-${i}-${NOW19}\"
    }"
done

curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",\"kind\":\"auth.succeeded\",\"occurred_at\":\"${NOW19}\",
    \"raw\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\"},
    \"normalized\":{\"user\":\"alice@corp.local\",\"source_ip\":\"203.0.113.7\",\"auth_type\":\"basic\"},
    \"dedupe_key\":\"phase7-join-success-${NOW19}\"
  }"

sleep 1

curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",\"kind\":\"process.created\",\"occurred_at\":\"${NOW19}\",
    \"raw\":{\"host\":\"lab-win10-01\",\"pid\":1111,\"ppid\":1,\"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",\"cmdline\":\"powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\",\"user\":\"alice@corp.local\"},
    \"normalized\":{
      \"host\":\"lab-win10-01\",
      \"pid\":1111,\"ppid\":1,
      \"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",
      \"cmdline\":\"powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\",
      \"user\":\"alice@corp.local\"
    },
    \"dedupe_key\":\"phase7-join-proc-${NOW19}\"
  }"

sleep 1

INCIDENTS19=$(curl -sf "${API}/v1/incidents?limit=10")
KINDS19=$(echo "${INCIDENTS19}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print(','.join(i['kind'] for i in data['items']))
")

echo "${KINDS19}" | grep -q "identity_compromise" \
  && pass "identity_compromise incident opened (join correlator fired)" \
  || fail "Expected identity_compromise incident, got kinds: ${KINDS19}"

echo "${KINDS19}" | grep -qv "endpoint_compromise" \
  && pass "No standalone endpoint_compromise incident (join took precedence)" \
  || fail "Standalone endpoint_compromise should not have fired when join succeeded"

# ---------------------------------------------------------------------------
# Check 20: Sigma rule fires on encoded-PowerShell event
# ---------------------------------------------------------------------------
header "Check 20: Sigma detection fires"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  psql -U cybercat -d cybercat -c "TRUNCATE events, incidents CASCADE;" > /dev/null 2>&1 || true
docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null || true

NOW20=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

curl -s -o /dev/null -X POST "${API}/v1/events/raw" \
  -H "Content-Type: application/json" \
  -d "{
    \"source\":\"seeder\",\"kind\":\"process.created\",\"occurred_at\":\"${NOW20}\",
    \"raw\":{\"host\":\"lab-win10-01\",\"pid\":4321,\"ppid\":1,\"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",\"cmdline\":\"powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\"},
    \"normalized\":{
      \"host\":\"lab-win10-01\",\"pid\":4321,\"ppid\":1,
      \"image\":\"C:\\\\Windows\\\\System32\\\\powershell.exe\",
      \"cmdline\":\"powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\"
    },
    \"dedupe_key\":\"phase7-sigma-001-${NOW20}\"
  }"

sleep 1

SIGMA_DETS=$(curl -sf "${API}/v1/detections?rule_source=sigma&limit=50")
SIGMA_COUNT=$(echo "${SIGMA_DETS}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print(len(data['items']))
")
[ "${SIGMA_COUNT}" -ge 1 ] \
  && pass "At least 1 Sigma detection fired (count=${SIGMA_COUNT})" \
  || fail "Expected ≥1 Sigma detection, got ${SIGMA_COUNT}"

SIGMA_ID=$(echo "${SIGMA_DETS}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
for d in data['items']:
    sid = d.get('matched_fields',{}).get('sigma_id','')
    if sid: print(sid); break
")
[ -n "${SIGMA_ID}" ] \
  && pass "Sigma detection has sigma_id in matched_fields: ${SIGMA_ID}" \
  || fail "Sigma detection missing sigma_id in matched_fields"

# ---------------------------------------------------------------------------
# Check 21: Python and Sigma both fire on same event (co-fire)
# ---------------------------------------------------------------------------
header "Check 21: Sigma + Python co-fire on same event"

ALL_DETS=$(curl -sf "${API}/v1/detections?limit=100")
HAS_PY=$(echo "${ALL_DETS}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print('yes' if any(d['rule_source']=='py' for d in data['items']) else 'no')
")
HAS_SIGMA=$(echo "${ALL_DETS}" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print('yes' if any(d['rule_source']=='sigma' for d in data['items']) else 'no')
")

[ "${HAS_PY}" = "yes" ] \
  && pass "Python detection row present" \
  || fail "Expected Python detection row (rule_source=py)"

[ "${HAS_SIGMA}" = "yes" ] \
  && pass "Sigma detection row present" \
  || fail "Expected Sigma detection row (rule_source=sigma)"

echo ""
echo -e "${BOLD}Phase 7 smoke test complete — 21 checks passed.${RESET}"
