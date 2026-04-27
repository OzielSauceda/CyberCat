#!/usr/bin/env bash
# smoke_test_phase8.sh — Phase 8 end-to-end verification (27 checks)
# Requires: docker compose --profile wazuh up -d && WAZUH_BRIDGE_ENABLED=true in .env
# Usage: bash labs/smoke_test_phase8.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
COMPOSE="docker compose -f ${SCRIPT_DIR}/../infra/compose/docker-compose.yml"
INDEXER_PASS="${WAZUH_INDEXER_PASSWORD:-SecretPassword123!}"
INDEXER_URL="https://localhost:9200"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS_COUNT=0; FAIL_COUNT=0

check() {
  local n="$1"; local desc="$2"; shift 2
  if eval "$@" >/dev/null 2>&1; then
    echo -e "${GREEN}[PASS]${NC} Check $n: $desc"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo -e "${RED}[FAIL]${NC} Check $n: $desc"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# ── Phase 7 regression (checks 1–21) ─────────────────────────────────────────
echo "── Running Phase 7 regression ──────────────────────────────────────────"
source "${SCRIPT_DIR}/smoke_test_phase7.sh" 2>/dev/null || true

# ── Phase 8: bridge on ───────────────────────────────────────────────────────
echo ""
echo "── Phase 8 checks ───────────────────────────────────────────────────────"

# 22. Wazuh manager API is reachable (401 = manager up, just no creds supplied).
# Avoids MSYS path mangling that breaks agent_control exec from git bash.
check 22 "Manager API reachable on :55000" \
  "curl -sk -o /dev/null -w '%{http_code}' https://localhost:55000/ | grep -qE '(200|401|403)'"

# 23. Indexer cluster health green or yellow
check 23 "Indexer cluster health green/yellow" \
  "curl -sk -u admin:${INDEXER_PASS} ${INDEXER_URL}/_cluster/health | grep -E '(green|yellow)'"

# 24. Bridge enabled in CyberCat status endpoint
check 24 "/v1/wazuh/status.enabled == true" \
  "curl -sf ${BASE_URL}/v1/wazuh/status | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d['enabled']==True\""

# Reset counter so check 25 measures delta from this point, not a stale total.
echo "  Resetting wazuh_cursor counter baseline..."
$COMPOSE --profile wazuh exec -T postgres \
  psql -U cybercat -d cybercat \
  -c "UPDATE wazuh_cursor SET events_ingested_total=0, events_dropped_total=0 WHERE id='singleton';" \
  > /dev/null 2>&1 || true

# 25–27. Fire brute-force + success scenario via lab-debian, then verify events.
# Uses realuser (known password) so we get both auth.failed bursts AND auth.succeeded,
# which together trigger the identity_compromise correlator.
echo "  Firing SSH brute-force + success scenario (realuser) from lab-debian..."
$COMPOSE --profile wazuh exec -T lab-debian bash -c '
  for i in 1 2 3 4; do
    sshpass -p wrongpassword ssh \
      -o StrictHostKeyChecking=no \
      -o ConnectTimeout=3 \
      -o PreferredAuthentications=password \
      -o PubkeyAuthentication=no \
      realuser@localhost true 2>/dev/null || true
  done
  sshpass -p lab123 ssh \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=3 \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    realuser@localhost true 2>/dev/null || true
' 2>/dev/null || echo "  (lab-debian exec failed — may not be running)"

echo "  Waiting 30s for events to propagate and correlate..."
sleep 30

INGESTED=$(curl -sf "${BASE_URL}/v1/wazuh/status" | python3 -c "import sys,json; print(json.load(sys.stdin)['events_ingested_total'])" 2>/dev/null || echo "0")
check 25 "events_ingested_total advanced since reset (got ${INGESTED})" \
  "[ '${INGESTED}' -gt 0 ]"

AUTH_FAILED_COUNT=$(curl -sf "${BASE_URL}/v1/events?source=wazuh&kind=auth.failed" 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data.get('items', [])))" 2>/dev/null || echo "0")
check 26 ">=1 auth.failed events with source=wazuh (got ${AUTH_FAILED_COUNT})" \
  "[ '${AUTH_FAILED_COUNT}' -ge 1 ]"

# 27. identity_compromise incident created with wazuh-sourced events.
# Requires: 4+ auth.failed (burst detection) + auth.succeeded (anomalous source)
# for the same user → identity_compromise correlator fires.
INCIDENT_JSON=$(curl -sf "${BASE_URL}/v1/incidents?kind=identity_compromise" 2>/dev/null || echo '{"items":[]}')
INCIDENT_COUNT=$(echo "${INCIDENT_JSON}" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('items', [])))" 2>/dev/null || echo "0")
check 27 "identity_compromise incident present (got ${INCIDENT_COUNT})" \
  "[ '${INCIDENT_COUNT}' -ge 1 ]"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "── Results ──────────────────────────────────────────────────────────────"
echo -e "  Passed: ${GREEN}${PASS_COUNT}${NC}  Failed: ${RED}${FAIL_COUNT}${NC}"
if [ "${FAIL_COUNT}" -eq 0 ]; then
  echo -e "${GREEN}All checks passed.${NC}"
  exit 0
else
  echo -e "${RED}${FAIL_COUNT} check(s) failed.${NC}"
  exit 1
fi
