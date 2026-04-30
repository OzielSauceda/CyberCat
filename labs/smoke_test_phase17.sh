#!/usr/bin/env bash
# Phase 17 smoke test — first-run experience: auto-seed + welcome page +
#                       glossary page + demo-data wipe.
#
# Run from the repo root: bash labs/smoke_test_phase17.sh
#
# Prereq: clean stack with empty volumes, then ./start.sh.
#         CCT_AUTOSEED_DEMO=true (default in dev compose).
#         If AUTH_REQUIRED=true: SMOKE_API_TOKEN in labs/.smoke-env must
#         have role=admin (the demo-wipe endpoint requires admin).
#
# Ordering note (per ADR-0014 §6): this smoke is intended to run *first*
# in any aggregate runner. Pre-existing smokes either export
# CCT_AUTOSEED_DEMO=false or call DELETE /v1/admin/demo-data before
# their first ingest.
#
# Verifies:
#   1. Backend healthy.
#   2. Auto-seed populated events on empty-volume cold start.
#   3. /v1/admin/demo-status reports active=true (Redis seed marker set).
#   4. Welcome page (frontend GET /) returns 200 with welcome markers.
#   5. Glossary page (frontend GET /help) returns 200 with glossary content.
#   6. Auto-seed produced at least one incident (the credential_theft_chain).
#   7. DELETE /v1/admin/demo-data → 204; events / incidents tables empty;
#      seed marker cleared; users + api_tokens preserved.

set -euo pipefail

API="${CYBERCAT_API:-http://localhost:8000}"
FRONTEND="${CYBERCAT_FRONTEND:-http://localhost:3000}"
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
# 1. Backend healthy
# ---------------------------------------------------------------------------
header "Backend health"
http_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/healthz")
[ "$http_status" = "200" ] && pass "Backend /healthz returns 200" \
    || { fail "Backend not healthy (HTTP $http_status) — run ./start.sh first"; exit 1; }

# ---------------------------------------------------------------------------
# 2. Auto-seed populated events
# ---------------------------------------------------------------------------
header "Auto-seed populated events"
EV_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?limit=1") \
    || { fail "GET /v1/events failed"; exit 1; }
EV_TOTAL=$(echo "$EV_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

if [ "$EV_TOTAL" -ge 1 ]; then
    pass "Backend has $EV_TOTAL seeded events"
else
    fail "Expected seeded events on cold start, got 0 — CCT_AUTOSEED_DEMO=true on a fresh volume?"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Seed marker active (Redis key cybercat:demo_active)
# ---------------------------------------------------------------------------
header "Seed marker: GET /v1/admin/demo-status"
DS_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/admin/demo-status") \
    || { fail "GET /v1/admin/demo-status failed"; exit 1; }
DS_ACTIVE=$(echo "$DS_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["active"])')

if [ "$DS_ACTIVE" = "True" ]; then
    pass "demo-status reports active=true (Redis seed marker set)"
else
    fail "demo-status active=$DS_ACTIVE — expected True on a fresh seeded volume"
    exit 1
fi

# Cross-check: Redis key cybercat:demo_active is set
DEMO_KEY=$(docker compose -f "${COMPOSE_FILE}" exec -T redis \
    redis-cli GET cybercat:demo_active 2>/dev/null | tr -d '\r')
if [ -n "$DEMO_KEY" ] && [ "$DEMO_KEY" != "(nil)" ]; then
    pass "Redis key cybercat:demo_active is set (= '$DEMO_KEY')"
else
    fail "Redis key cybercat:demo_active is not set"
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Welcome page returns 200 with welcome markers
# ---------------------------------------------------------------------------
header "Frontend welcome page"
WELCOME=$(curl -s -o /tmp/cct_welcome.html -w "%{http_code}" "${FRONTEND}/")
if [ "$WELCOME" = "200" ]; then
    pass "Frontend GET / returns 200"
else
    fail "Frontend GET / returned $WELCOME — is the frontend container up?"
    exit 1
fi

# Welcome page should advertise CYBERCAT logotype + at least one welcome-page label.
# Markers chosen: "CYBERCAT" (logotype) AND "Quick Access" (welcome-page section header).
if grep -q "CYBERCAT" /tmp/cct_welcome.html && grep -q "Quick Access" /tmp/cct_welcome.html; then
    pass "Welcome page contains CYBERCAT logotype and 'Quick Access' section"
else
    fail "Welcome page missing expected markers (CYBERCAT / 'Quick Access')"
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Glossary page returns 200 with glossary content
# ---------------------------------------------------------------------------
header "Frontend glossary page"
HELP=$(curl -s -o /tmp/cct_help.html -w "%{http_code}" "${FRONTEND}/help")
if [ "$HELP" = "200" ]; then
    pass "Frontend GET /help returns 200"
else
    fail "Frontend GET /help returned $HELP"
    exit 1
fi

# Glossary should render terms via lib/glossary.ts. Check for a few canonical
# entries that are guaranteed to exist (incident, detection).
if grep -qi "incident" /tmp/cct_help.html && grep -qi "detection" /tmp/cct_help.html; then
    pass "Glossary page contains 'incident' and 'detection' terms"
else
    fail "Glossary page missing expected terms"
    exit 1
fi

# ---------------------------------------------------------------------------
# 6. Auto-seed produced at least one incident (credential_theft_chain)
# ---------------------------------------------------------------------------
header "Seeded incident exists"
INC_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents?limit=10") \
    || { fail "GET /v1/incidents failed"; exit 1; }
INC_TOTAL=$(echo "$INC_RESP" | $PY -c 'import json,sys; print(len(json.load(sys.stdin)["items"]))')

if [ "$INC_TOTAL" -ge 1 ]; then
    pass "Backend has $INC_TOTAL seeded incident(s)"
else
    fail "Expected at least one seeded incident, got $INC_TOTAL"
    exit 1
fi

# ---------------------------------------------------------------------------
# 7. Capture pre-wipe users/api_tokens counts (must be preserved)
# ---------------------------------------------------------------------------
header "Pre-wipe: capture users + api_tokens row counts"
USERS_BEFORE=$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -tAc "SELECT COUNT(*) FROM users;" | tr -d '\r')
TOKENS_BEFORE=$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -tAc "SELECT COUNT(*) FROM api_tokens;" | tr -d '\r')
pass "users=$USERS_BEFORE  api_tokens=$TOKENS_BEFORE"

# ---------------------------------------------------------------------------
# 8. DELETE /v1/admin/demo-data
#    NOTE: requires role=admin when AUTH_REQUIRED=true. SystemUser passthrough
#    when AUTH_REQUIRED=false (default).
# ---------------------------------------------------------------------------
header "Wipe demo data (DELETE /v1/admin/demo-data)"
WIPE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
    "${AUTH_HEADER[@]}" "${API}/v1/admin/demo-data")

if [ "$WIPE_STATUS" = "204" ]; then
    pass "DELETE /v1/admin/demo-data returned 204"
elif [ "$WIPE_STATUS" = "403" ]; then
    fail "DELETE /v1/admin/demo-data returned 403 — SMOKE_API_TOKEN role is not admin?"
    exit 1
else
    fail "DELETE /v1/admin/demo-data returned $WIPE_STATUS (expected 204)"
    exit 1
fi

# ---------------------------------------------------------------------------
# 9. Post-wipe assertions
# ---------------------------------------------------------------------------
header "Post-wipe state"

EV_AFTER=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?limit=1" \
    | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')
[ "$EV_AFTER" = "0" ] && pass "events table is empty after wipe" \
    || { fail "events still has $EV_AFTER rows after wipe"; exit 1; }

INC_AFTER=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents?limit=1" \
    | $PY -c 'import json,sys; print(len(json.load(sys.stdin)["items"]))')
[ "$INC_AFTER" = "0" ] && pass "incidents table is empty after wipe" \
    || { fail "incidents still has $INC_AFTER rows after wipe"; exit 1; }

DS_AFTER=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/admin/demo-status" \
    | $PY -c 'import json,sys; print(json.load(sys.stdin)["active"])')
[ "$DS_AFTER" = "False" ] && pass "demo-status active=False after wipe (seed marker cleared)" \
    || { fail "demo-status active=$DS_AFTER after wipe"; exit 1; }

DEMO_KEY_AFTER=$(docker compose -f "${COMPOSE_FILE}" exec -T redis \
    redis-cli GET cybercat:demo_active 2>/dev/null | tr -d '\r')
if [ -z "$DEMO_KEY_AFTER" ] || [ "$DEMO_KEY_AFTER" = "" ]; then
    pass "Redis key cybercat:demo_active is cleared"
else
    fail "Redis key cybercat:demo_active still set: '$DEMO_KEY_AFTER'"
    exit 1
fi

# users + api_tokens preserved (the contract from ADR-0014 §5).
USERS_AFTER=$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -tAc "SELECT COUNT(*) FROM users;" | tr -d '\r')
TOKENS_AFTER=$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -tAc "SELECT COUNT(*) FROM api_tokens;" | tr -d '\r')

if [ "$USERS_AFTER" = "$USERS_BEFORE" ]; then
    pass "users count preserved ($USERS_AFTER)"
else
    fail "users count changed: before=$USERS_BEFORE after=$USERS_AFTER (must be preserved)"
    exit 1
fi

if [ "$TOKENS_AFTER" = "$TOKENS_BEFORE" ]; then
    pass "api_tokens count preserved ($TOKENS_AFTER)"
else
    fail "api_tokens count changed: before=$TOKENS_BEFORE after=$TOKENS_AFTER (must be preserved)"
    exit 1
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}=== Summary ===${RESET}"
echo -e "${GREEN}Passes:${RESET}   $PASSES"
echo -e "${RED}Failures:${RESET} $FAILURES"

if [ "$FAILURES" -gt 0 ]; then
    exit 1
fi
exit 0
