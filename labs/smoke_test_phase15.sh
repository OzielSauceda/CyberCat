#!/usr/bin/env bash
# Phase 15 smoke test — Recommended Response Actions
# Run from the repo root: bash labs/smoke_test_phase15.sh
# Requires: docker compose up -d (infra/compose/) and a running backend
#
# Reproduces the credential_theft_chain scenario inline via curl (not via the
# simulator) so it has no host-side python dependencies. Verifies the recommender
# against both incidents the scenario produces:
#   - identity_compromise (carries source_ip → block_observable recommended)
#   - identity_endpoint_chain (carries user+host → quarantine/invalidate flow)
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

post_event() {
    local body="$1"
    curl -sf "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
        -H "Content-Type: application/json" \
        -d "$body" > /dev/null
}

USER_NAME="alice"
HOST_NAME="workstation-42"
ATTACKER_IP="203.0.113.42"
WORKSTATION_IP="10.0.0.50"

# ---------------------------------------------------------------------------
# 1. Backend healthcheck
# ---------------------------------------------------------------------------
header "Backend health"
http_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/healthz")
[ "$http_status" = "200" ] && pass "Backend is healthy" \
    || { fail "Backend not healthy (HTTP $http_status)"; exit 1; }

# ---------------------------------------------------------------------------
# 2. Setup: truncate DB and flush Redis
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
# 3. Register lab assets (user + host + observable IP)
# ---------------------------------------------------------------------------
header "Register lab assets"
for asset in "{\"kind\":\"user\",\"natural_key\":\"${USER_NAME}\"}" \
             "{\"kind\":\"host\",\"natural_key\":\"${HOST_NAME}\"}" \
             "{\"kind\":\"observable\",\"natural_key\":\"${ATTACKER_IP}\"}"; do
    curl -sf "${AUTH_HEADER[@]}" -X POST "${API}/v1/lab/assets" \
        -H "Content-Type: application/json" \
        -d "$asset" > /dev/null \
        || warn "Lab asset register failed (may already exist): $asset"
done
pass "Lab assets registered (user, host, observable IP)"

# ---------------------------------------------------------------------------
# 4. Reproduce credential_theft_chain inline
# ---------------------------------------------------------------------------
header "Fire credential_theft_chain events"

for i in 1 2 3 4 5 6; do
    post_event "{\"source\":\"seeder\",\"kind\":\"auth.failed\",\"occurred_at\":\"2026-04-28T11:00:0${i}Z\",\"raw\":{},\"normalized\":{\"user\":\"${USER_NAME}\",\"source_ip\":\"${ATTACKER_IP}\",\"auth_type\":\"ssh\"},\"dedupe_key\":\"phase15:cred-chain:auth.failed:${i}\"}"
done
post_event "{\"source\":\"seeder\",\"kind\":\"auth.succeeded\",\"occurred_at\":\"2026-04-28T11:01:00Z\",\"raw\":{},\"normalized\":{\"user\":\"${USER_NAME}\",\"source_ip\":\"${ATTACKER_IP}\",\"auth_type\":\"ssh\"},\"dedupe_key\":\"phase15:cred-chain:auth.succeeded\"}"
post_event "{\"source\":\"seeder\",\"kind\":\"session.started\",\"occurred_at\":\"2026-04-28T11:01:15Z\",\"raw\":{},\"normalized\":{\"user\":\"${USER_NAME}\",\"host\":\"${HOST_NAME}\",\"session_id\":\"phase15-alice-01\"},\"dedupe_key\":\"phase15:cred-chain:session.started\"}"
post_event "{\"source\":\"seeder\",\"kind\":\"process.created\",\"occurred_at\":\"2026-04-28T11:03:00Z\",\"raw\":{},\"normalized\":{\"host\":\"${HOST_NAME}\",\"pid\":4242,\"ppid\":2828,\"image\":\"powershell.exe\",\"cmdline\":\"powershell.exe -enc SGVsbG8gV29ybGQ=\",\"user\":\"${USER_NAME}\"},\"dedupe_key\":\"phase15:cred-chain:process.enc-ps\"}"
post_event "{\"source\":\"seeder\",\"kind\":\"process.created\",\"occurred_at\":\"2026-04-28T11:04:00Z\",\"raw\":{},\"normalized\":{\"host\":\"${HOST_NAME}\",\"pid\":4243,\"ppid\":4242,\"image\":\"net.exe\",\"cmdline\":\"net use\",\"user\":\"${USER_NAME}\"},\"dedupe_key\":\"phase15:cred-chain:process.net-use\"}"
post_event "{\"source\":\"seeder\",\"kind\":\"network.connection\",\"occurred_at\":\"2026-04-28T11:04:10Z\",\"raw\":{},\"normalized\":{\"host\":\"${HOST_NAME}\",\"src_ip\":\"${WORKSTATION_IP}\",\"dst_ip\":\"${ATTACKER_IP}\",\"dst_port\":4444,\"proto\":\"tcp\"},\"dedupe_key\":\"phase15:cred-chain:network.c2\"}"

pass "Scenario events fired"
# Wait for correlator + auto-proposed actions to settle
sleep 5

# ---------------------------------------------------------------------------
# 5. Locate both incidents
# ---------------------------------------------------------------------------
header "Locate incidents"
INC_LIST=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents?limit=50") \
    || { fail "GET /v1/incidents failed"; exit 1; }

CHAIN_ID=$(echo "$INC_LIST" | $PY -c '
import json, sys
items = json.load(sys.stdin)["items"]
chain = [i for i in items if i["kind"] == "identity_endpoint_chain"]
if not chain:
    sys.exit(1)
print(chain[0]["id"])
') || { fail "identity_endpoint_chain incident not found"; exit 1; }
pass "Chain incident: $CHAIN_ID"

IDENTITY_ID=$(echo "$INC_LIST" | $PY -c '
import json, sys
items = json.load(sys.stdin)["items"]
ic = [i for i in items if i["kind"] == "identity_compromise"]
if not ic:
    sys.exit(1)
print(ic[0]["id"])
') || { fail "identity_compromise incident not found"; exit 1; }
pass "Identity incident: $IDENTITY_ID"

# ---------------------------------------------------------------------------
# 6. Recommendations endpoint — chain incident
# ---------------------------------------------------------------------------
header "Recommendations: chain incident"
CHAIN_RECS_FILE=$(mktemp)
RECS_RESP=$(curl -s "${AUTH_HEADER[@]}" -w "\n__HTTP__%{http_code}" \
    "${API}/v1/incidents/${CHAIN_ID}/recommended-actions")
echo "$RECS_RESP" | sed '$d' > "$CHAIN_RECS_FILE"
RECS_STATUS=$(echo "$RECS_RESP" | tail -1 | sed 's/__HTTP__//')

[ "$RECS_STATUS" = "200" ] && pass "GET /recommended-actions returns 200 (chain)" \
    || { fail "Expected 200, got $RECS_STATUS"; cat "$CHAIN_RECS_FILE"; exit 1; }

CHAIN_LEN=$($PY -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$CHAIN_RECS_FILE")
[ "$CHAIN_LEN" -ge 1 ] && pass "Chain has >= 1 recommendation (got $CHAIN_LEN)" \
    || fail "Chain expected >= 1 recommendation, got $CHAIN_LEN"

# All-fields populated check
FIELDS_ASSERT=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
required = ["kind", "params", "rationale", "classification", "classification_reason", "priority"]
missing = []
for i, r in enumerate(recs):
    for f in required:
        if r.get(f) is None or r.get(f) == "":
            missing.append("#{}.{}".format(i, f))
print("ok" if not missing else "missing: " + ",".join(missing))
' "$CHAIN_RECS_FILE")
[ "$FIELDS_ASSERT" = "ok" ] \
    && pass "All chain recs have classification/rationale/priority populated" \
    || fail "Field check (chain): $FIELDS_ASSERT"

# Excluded-kind check on chain recs
EXCLUDED_ASSERT=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
forbidden = {"tag_incident", "elevate_severity", "kill_process_lab"}
hits = [r["kind"] for r in recs if r["kind"] in forbidden]
print("ok" if not hits else "found: " + ",".join(hits))
' "$CHAIN_RECS_FILE")
[ "$EXCLUDED_ASSERT" = "ok" ] \
    && pass "No excluded kinds (chain)" \
    || fail "Excluded-kind leak (chain): $EXCLUDED_ASSERT"

# Sorted-by-priority check
SORTED_ASSERT=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
priorities = [r["priority"] for r in recs]
print("ok" if priorities == sorted(priorities) else "got: " + str(priorities))
' "$CHAIN_RECS_FILE")
[ "$SORTED_ASSERT" = "ok" ] && pass "Chain recs sorted by priority asc" \
    || fail "Sorted check: $SORTED_ASSERT"

# ---------------------------------------------------------------------------
# 7. Recommendations endpoint — identity_compromise (block_observable lives here)
# ---------------------------------------------------------------------------
header "Recommendations: identity_compromise incident"
ID_RECS_FILE=$(mktemp)
curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents/${IDENTITY_ID}/recommended-actions" \
    > "$ID_RECS_FILE" \
    || { fail "GET /recommended-actions failed for identity"; exit 1; }
pass "GET /recommended-actions returns 200 (identity)"

ID_LEN=$($PY -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$ID_RECS_FILE")
[ "$ID_LEN" -ge 1 ] && pass "Identity has >= 1 recommendation (got $ID_LEN)" \
    || fail "Identity expected >= 1 rec, got $ID_LEN"

TOP_ASSERT=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
top = recs[0]
ok = top["kind"] == "block_observable" and top["params"].get("value") == "203.0.113.42"
if ok:
    print("ok")
else:
    print("got kind={} value={}".format(top.get("kind"), top.get("params", {}).get("value")))
' "$ID_RECS_FILE")
[ "$TOP_ASSERT" = "ok" ] \
    && pass "Top identity rec is block_observable on 203.0.113.42" \
    || fail "Top rec mismatch: $TOP_ASSERT"

# ---------------------------------------------------------------------------
# 8. Propose + execute the block_observable recommendation
# ---------------------------------------------------------------------------
header "Propose + execute block_observable from identity recs"

PROPOSE_BODY=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
top = recs[0]
out = {"incident_id": sys.argv[2], "kind": top["kind"], "params": top["params"]}
print(json.dumps(out))
' "$ID_RECS_FILE" "$IDENTITY_ID")

PROPOSE_RESP=$(curl -sf "${AUTH_HEADER[@]}" -X POST "${API}/v1/responses" \
    -H "Content-Type: application/json" \
    -d "$PROPOSE_BODY") \
    || { fail "Propose failed"; exit 1; }
ACTION_ID=$(echo "$PROPOSE_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["action"]["id"])')
[ -n "$ACTION_ID" ] && pass "Proposed action $ACTION_ID" \
    || { fail "Could not parse action id"; exit 1; }

EXEC_RESP=$(curl -sf "${AUTH_HEADER[@]}" -X POST "${API}/v1/responses/${ACTION_ID}/execute") \
    || { fail "Execute failed"; exit 1; }
EXEC_STATUS=$(echo "$EXEC_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["action"]["status"])')
[ "$EXEC_STATUS" = "executed" ] && pass "Action executed (status=executed)" \
    || fail "Expected status=executed, got $EXEC_STATUS"

# ---------------------------------------------------------------------------
# 9. Recommendations refetch — block_observable should now be filtered
# ---------------------------------------------------------------------------
header "Post-execute: recommendation filtered out"
sleep 1
RECS2_FILE=$(mktemp)
curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents/${IDENTITY_ID}/recommended-actions" \
    > "$RECS2_FILE"

GONE=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
hit = any(r["kind"] == "block_observable" and r["params"].get("value") == "203.0.113.42" for r in recs)
print("gone" if not hit else "still-present")
' "$RECS2_FILE")
[ "$GONE" = "gone" ] && pass "block_observable on ${ATTACKER_IP} filtered post-execute" \
    || fail "block_observable on ${ATTACKER_IP} still recommended after execute"

# ---------------------------------------------------------------------------
# 10. Revert — recommendation should reappear
# ---------------------------------------------------------------------------
header "Post-revert: recommendation re-eligible"
REVERT_RESP=$(curl -sf "${AUTH_HEADER[@]}" -X POST "${API}/v1/responses/${ACTION_ID}/revert") \
    || { fail "Revert failed"; exit 1; }
REVERT_STATUS=$(echo "$REVERT_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["action"]["status"])')
[ "$REVERT_STATUS" = "reverted" ] && pass "Action reverted (status=reverted)" \
    || fail "Expected status=reverted, got $REVERT_STATUS"

sleep 1
RECS3_FILE=$(mktemp)
curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents/${IDENTITY_ID}/recommended-actions" \
    > "$RECS3_FILE"

BACK=$($PY -c '
import json, sys
recs = json.load(open(sys.argv[1]))
hit = any(r["kind"] == "block_observable" and r["params"].get("value") == "203.0.113.42" for r in recs)
print("back" if hit else "missing")
' "$RECS3_FILE")
[ "$BACK" = "back" ] && pass "block_observable on ${ATTACKER_IP} reappeared post-revert" \
    || fail "block_observable on ${ATTACKER_IP} did not reappear after revert"

# ---------------------------------------------------------------------------
# 11. 404 path — unknown incident id
# ---------------------------------------------------------------------------
header "404 for unknown incident"
NOT_FOUND_STATUS=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" \
    "${API}/v1/incidents/00000000-0000-0000-0000-000000000000/recommended-actions")
[ "$NOT_FOUND_STATUS" = "404" ] && pass "Unknown incident id returns 404" \
    || fail "Expected 404, got $NOT_FOUND_STATUS"

rm -f "$CHAIN_RECS_FILE" "$ID_RECS_FILE" "$RECS2_FILE" "$RECS3_FILE"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Phase 15 smoke test complete: ${GREEN}${PASSES} passed${RESET}, ${RED}${FAILURES} failed${RESET}"
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1
