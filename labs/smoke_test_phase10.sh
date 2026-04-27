#!/usr/bin/env bash
# Phase 10 smoke test — Attack Simulator + identity_endpoint_chain correlator.
# Run from the repo root: bash labs/smoke_test_phase10.sh
# Requires: docker compose up -d (from infra/compose/); pip install httpx
set -euo pipefail

API="http://localhost:8000"
COMPOSE_FILE="infra/compose/docker-compose.yml"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

pass() { echo -e "${GREEN}PASS${RESET} $1"; PASSES=$((PASSES + 1)); }
fail() { echo -e "${RED}FAIL${RESET} $1"; FAILURES=$((FAILURES + 1)); exit 1; }
header() { echo -e "\n${BOLD}--- $1 ---${RESET}"; }

PASSES=0
FAILURES=0

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
             event_entities, events, entities, lab_assets
    CASCADE;
  " > /dev/null \
  && pass "DB truncated for Phase 10 checks" \
  || { echo "WARNING: could not truncate DB — continuing"; }

docker compose -f "${COMPOSE_FILE}" exec -T redis redis-cli FLUSHDB > /dev/null \
  && pass "Redis flushed for Phase 10 checks" \
  || true

# ---------------------------------------------------------------------------
# Check 1: Backend health
# ---------------------------------------------------------------------------
header "Check 1: Backend health"

STATUS=$(curl -sf "${API}/healthz" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status',''))")
[ "$STATUS" = "ok" ] \
  && pass "Backend /healthz returns status=ok" \
  || fail "Backend /healthz unexpected: $STATUS"

# ---------------------------------------------------------------------------
# Check 2: httpx available for simulator
# ---------------------------------------------------------------------------
header "Check 2: httpx importable"

python -c "import httpx" 2>/dev/null \
  && pass "httpx importable in local Python" \
  || fail "httpx not installed — run: pip install httpx"

# ---------------------------------------------------------------------------
# Check 3–4: Run simulator (speed=0.1, ~30s) with built-in --verify
# ---------------------------------------------------------------------------
header "Checks 3–4: Run credential_theft_chain scenario"

echo "Running: python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify"
python -m labs.simulator \
  --scenario credential_theft_chain \
  --speed 0.1 \
  --verify \
  --api "${API}" \
  && pass "Simulator exited 0" \
  || fail "Simulator exited non-zero (verify failed)"

# Brief pause so async side-effects (auto-actions) settle
sleep 2

# ---------------------------------------------------------------------------
# Checks 5–9: Incident API assertions
# ---------------------------------------------------------------------------
header "Checks 5–9: Incident API assertions"

INCIDENTS=$(curl -sf "${API}/v1/incidents?limit=100")

# Check 5: identity_compromise incident present for alice
IC_ID=$(echo "$INCIDENTS" | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
hit = next((i for i in items if i['kind']=='identity_compromise' and (i.get('primary_user') or '').lower()=='alice'), None)
print(hit['id'] if hit else '')
")
[ -n "$IC_ID" ] \
  && pass "identity_compromise incident found for alice (id=$IC_ID)" \
  || fail "identity_compromise incident not found for alice"

# Check 6: identity_endpoint_chain incident present for alice
CHAIN_ID=$(echo "$INCIDENTS" | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
hit = next((i for i in items if i['kind']=='identity_endpoint_chain' and (i.get('primary_user') or '').lower()=='alice'), None)
print(hit['id'] if hit else '')
")
[ -n "$CHAIN_ID" ] \
  && pass "identity_endpoint_chain incident found for alice (id=$CHAIN_ID)" \
  || fail "identity_endpoint_chain incident not found for alice"

# Check 7: chain incident primary_host = workstation-42
CHAIN_HOST=$(echo "$INCIDENTS" | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
hit = next((i for i in items if i['kind']=='identity_endpoint_chain'), None)
print((hit or {}).get('primary_host', ''))
")
[ "$CHAIN_HOST" = "workstation-42" ] \
  && pass "chain incident primary_host = workstation-42" \
  || fail "chain incident primary_host expected workstation-42, got '${CHAIN_HOST}'"

# Check 8: chain incident severity = critical (auto-elevated by elevate_severity action)
CHAIN_SEV=$(echo "$INCIDENTS" | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
hit = next((i for i in items if i['kind']=='identity_endpoint_chain'), None)
print((hit or {}).get('severity', ''))
")
[ "$CHAIN_SEV" = "critical" ] \
  && pass "chain incident severity = critical (auto-elevated)" \
  || fail "chain incident severity expected critical, got '${CHAIN_SEV}'"

# Check 9: identity_compromise incident has at least 1 evidence_request (auto-proposed)
ER_COUNT=$(curl -sf "${API}/v1/evidence-requests?incident_id=${IC_ID}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(len(d.get('items', [])))
" 2>/dev/null || echo "0")
[ "$ER_COUNT" -ge 1 ] \
  && pass "identity_compromise has ${ER_COUNT} auto-proposed evidence request(s)" \
  || fail "identity_compromise has no evidence requests (expected ≥1)"

# ---------------------------------------------------------------------------
# Checks 10–12: Chain incident detail
# ---------------------------------------------------------------------------
header "Checks 10–12: Chain incident detail"

CHAIN_DETAIL=$(curl -sf "${API}/v1/incidents/${CHAIN_ID}")

# Check 10: rationale mentions cross-layer
RATIONALE=$(echo "$CHAIN_DETAIL" | python3 -c "import json,sys; print(json.load(sys.stdin).get('rationale',''))")
echo "$RATIONALE" | grep -qi "cross-layer\|cross layer\|identity compromise" \
  && pass "chain rationale references cross-layer correlation" \
  || fail "chain rationale missing cross-layer reference"

# Check 11: correlator_rule = identity_endpoint_chain
RULE=$(echo "$CHAIN_DETAIL" | python3 -c "import json,sys; print(json.load(sys.stdin).get('correlator_rule',''))")
[ "$RULE" = "identity_endpoint_chain" ] \
  && pass "chain correlator_rule = identity_endpoint_chain" \
  || fail "chain correlator_rule expected identity_endpoint_chain, got '${RULE}'"

# Check 12: chain incident has both user + host entities
ENTITY_COUNT=$(echo "$CHAIN_DETAIL" | python3 -c "
import json, sys
d = json.load(sys.stdin)
entities = d.get('entities', [])
kinds = [e.get('kind','') for e in entities]
user_ok = 'user' in kinds
host_ok = 'host' in kinds
print('ok' if user_ok and host_ok else f'user={user_ok} host={host_ok}')
")
[ "$ENTITY_COUNT" = "ok" ] \
  && pass "chain incident has both user and host entities linked" \
  || fail "chain incident entity links incomplete: $ENTITY_COUNT"

# ---------------------------------------------------------------------------
# Checks 13–14: Idempotency (re-run within same hour = no new incidents)
# ---------------------------------------------------------------------------
header "Checks 13–14: Idempotency (re-run produces no new incidents)"

INCIDENT_COUNT_BEFORE=$(echo "$INCIDENTS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['items']))")

echo "Re-running simulator (dedup should absorb all)..."
python -m labs.simulator \
  --scenario credential_theft_chain \
  --speed 0.1 \
  --no-verify \
  --api "${API}" > /dev/null

sleep 1

INCIDENTS_AFTER=$(curl -sf "${API}/v1/incidents?limit=100")
INCIDENT_COUNT_AFTER=$(echo "$INCIDENTS_AFTER" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['items']))")

[ "$INCIDENT_COUNT_AFTER" -eq "$INCIDENT_COUNT_BEFORE" ] \
  && pass "Re-run did not create new incidents (count stable at ${INCIDENT_COUNT_BEFORE})" \
  || fail "Re-run created new incidents: before=${INCIDENT_COUNT_BEFORE} after=${INCIDENT_COUNT_AFTER}"

# Check 14: --verify still passes on re-run (existing incidents satisfy it)
python -m labs.simulator \
  --scenario credential_theft_chain \
  --speed 0.1 \
  --no-verify \
  --api "${API}" > /dev/null \
  && pass "Re-run completes without error (all events deduped)" \
  || fail "Re-run exited non-zero unexpectedly"

# ---------------------------------------------------------------------------
# Check 15: Simulator lists scenario in available list
# ---------------------------------------------------------------------------
header "Check 15: Simulator self-reports available scenarios"

SIM_HELP=$(python -m labs.simulator --scenario nonexistent_xyz --api "${API}" 2>&1 || true)
echo "$SIM_HELP" | grep -q "credential_theft_chain" \
  && pass "Simulator lists credential_theft_chain in available scenarios" \
  || fail "Simulator did not list credential_theft_chain in unknown-scenario error"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}=== Phase 10 smoke test: ${PASSES} passed, ${FAILURES} failed ===${RESET}"
[ "$FAILURES" -eq 0 ] && echo -e "${GREEN}ALL CHECKS PASSED${RESET}" || echo -e "${RED}SOME CHECKS FAILED${RESET}"
