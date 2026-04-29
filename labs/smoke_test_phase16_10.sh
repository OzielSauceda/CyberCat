#!/usr/bin/env bash
# Phase 16.10 smoke test — conntrack-driven network telemetry
# Run from the repo root: bash labs/smoke_test_phase16_10.sh
#
# Prereq: ./start.sh (default profile = core+agent)
# Honours labs/.smoke-env for SMOKE_API_TOKEN if AUTH_REQUIRED=true.
#
# Verifies the conntrack path end-to-end:
#   synthetic conntrack lines → /var/log/conntrack.log (lab_logs volume)
#     → cct-agent conntrack source (tail + parse_line)
#     → POST /v1/events/raw (source=direct, kind=network.connection)
#     → backend ingest + entity extraction + py.blocked_observable_match
#
# Why synthetic injection: Docker Desktop on Windows / WSL2 does not expose
# the host kernel's nf_conntrack netlink to containers reliably across all
# environments. The agent code path is identical regardless of whether lines
# come from the real kernel or a here-doc — synthetic injection validates
# parse + ship + detect end-to-end. On a Linux host where conntrack netlink
# IS available, the same script works unchanged because the agent just tails
# whatever lines arrive at the file (real or injected).
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
# 1. Containers up + Wazuh stays dormant
# ---------------------------------------------------------------------------
header "Containers"
http_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/healthz")
[ "$http_status" = "200" ] && pass "Backend /healthz returns 200" \
    || { fail "Backend not healthy (HTTP $http_status) — run ./start.sh first"; exit 1; }

for c in compose-cct-agent-1 compose-lab-debian-1; do
    if docker ps --format "{{.Names}}" | grep -q "^${c}$"; then
        pass "${c} is running"
    else
        fail "${c} is not running — run ./start.sh first"
        exit 1
    fi
done

if docker ps --format "{{.Names}}" | grep -qE "^compose-wazuh-(manager|indexer)-1$"; then
    warn "Wazuh containers running — Phase 16 default is agent-only (--profile wazuh active?)"
else
    pass "Wazuh containers NOT running (default agent-only profile)"
fi

# ---------------------------------------------------------------------------
# 2. Ensure conntrack.log exists in lab-debian
# ---------------------------------------------------------------------------
header "Conntrack log file"
MSYS_NO_PATHCONV=1 docker exec compose-lab-debian-1 bash -c \
    'touch /var/log/conntrack.log && chmod 644 /var/log/conntrack.log' \
    && pass "conntrack.log exists in lab-debian (/var/log/conntrack.log)" \
    || { fail "could not create conntrack.log"; exit 1; }

if MSYS_NO_PATHCONV=1 docker exec compose-lab-debian-1 which conntrack > /dev/null 2>&1; then
    pass "conntrack binary is installed in lab-debian"
else
    fail "conntrack binary missing — Dockerfile out of date?"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Restart cct-agent so it picks up all three sources at startup
# ---------------------------------------------------------------------------
header "Agent restart for source pickup"
docker compose -f "${COMPOSE_FILE}" restart cct-agent > /dev/null 2>&1
echo "Waiting for agent banner..."

# Poll for the readiness line for up to 30s
SAW_BANNER=""
for _ in $(seq 1 30); do
    if docker logs compose-cct-agent-1 2>&1 | grep -q "agent ready, tailing.*conntrack.log"; then
        SAW_BANNER="yes"
        break
    fi
    sleep 1
done

if [ -n "$SAW_BANNER" ]; then
    pass "Agent banner shows conntrack.log being tailed"
    docker logs compose-cct-agent-1 --tail 5 2>&1 | grep -E "agent ready|sshd source|auditd source|conntrack source" || true
else
    fail "Agent did not log 'tailing ... conntrack.log' within 30s"
    docker logs compose-cct-agent-1 --tail 30 2>&1
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Truncate DB + flush Redis for clean assertion window
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
# 5. Pre-stage a blocked observable for 203.0.113.42 (the bad-egress dst)
#    The blocked_observables table FK-references actions(id) which itself
#    requires an incident — too much chaining for a smoke. Instead we seed
#    the detector's Redis cache directly. The detector reads Redis first
#    (cache TTL 30s) and only falls through to the DB on a cache miss, so
#    a populated cache is functionally equivalent for assertion purposes.
# ---------------------------------------------------------------------------
header "Pre-stage blocked observable (via Redis cache)"
docker compose -f "${COMPOSE_FILE}" exec -T redis \
    redis-cli SET cybercat:blocked_observables:active '["203.0.113.42"]' EX 120 > /dev/null \
    && pass "blocked_observable cache seeded with 203.0.113.42 (TTL 120s)" \
    || { fail "could not set Redis cache key"; exit 1; }

# ---------------------------------------------------------------------------
# 6. Inject 3 synthetic conntrack lines into /var/log/conntrack.log
#    - TCP NEW to 203.0.113.42:443 (the blocked dst)
#    - UDP NEW to 8.8.8.8:53 (clean traffic)
#    - NEW with loopback (must be dropped at the parser, never shipped)
# ---------------------------------------------------------------------------
header "Inject synthetic conntrack records"
TS=$(date +%s)
INJECT=$(cat <<EOF
[${TS}.001000]	[NEW] ipv4     2 tcp      6 120 SYN_SENT src=10.0.0.5 dst=203.0.113.42 sport=54321 dport=443 [UNREPLIED] src=203.0.113.42 dst=10.0.0.5 sport=443 dport=54321
[${TS}.002000]	[NEW] ipv4     2 udp      17 30 src=10.0.0.5 dst=8.8.8.8 sport=44321 dport=53 [UNREPLIED] src=8.8.8.8 dst=10.0.0.5 sport=53 dport=44321
[${TS}.003000]	[NEW] ipv4     2 udp      17 30 src=127.0.0.1 dst=127.0.0.11 sport=59999 dport=53 [UNREPLIED] src=127.0.0.11 dst=127.0.0.1 sport=53 dport=59999
EOF
)

MSYS_NO_PATHCONV=1 docker exec -i compose-lab-debian-1 bash -c \
    'cat >> /var/log/conntrack.log' <<<"$INJECT" \
    && pass "Injected 3 conntrack records (1 blocked-dst TCP + 1 clean UDP + 1 loopback)" \
    || { fail "could not write to conntrack.log"; exit 1; }

echo "Waiting 15s for agent → backend → entity extraction → detection..."
sleep 15

# ---------------------------------------------------------------------------
# 7. network.connection events arrived (source=direct), loopback NOT among them
# ---------------------------------------------------------------------------
header "Events: network.connection"
EV_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/events?source=direct&kind=network.connection&limit=50") \
    || { fail "GET /v1/events?kind=network.connection failed"; exit 1; }
EV_COUNT=$(echo "$EV_RESP" | $PY -c 'import json,sys; print(json.load(sys.stdin)["total"])')

if [ "$EV_COUNT" -ge 2 ]; then
    pass "Backend has $EV_COUNT direct network.connection events (>=2: blocked TCP + clean UDP)"
else
    fail "Expected >=2 direct network.connection events, got $EV_COUNT"
    docker logs compose-cct-agent-1 --tail 30 2>&1
    exit 1
fi

# Loopback line must have been dropped at the parser — it is not in the events table.
HAS_LOOPBACK=$(echo "$EV_RESP" | $PY -c '
import json, sys
data = json.load(sys.stdin)
items = data.get("items", [])
hit = any(
    (it.get("normalized") or {}).get("dst_ip") == "127.0.0.11"
    or (it.get("normalized") or {}).get("src_ip") == "127.0.0.1"
    for it in items
)
print("yes" if hit else "no")
')
if [ "$HAS_LOOPBACK" = "no" ]; then
    pass "Loopback record was dropped at parser (not in events table)"
else
    fail "Loopback record reached backend — parser filter regressed"
    exit 1
fi

# ---------------------------------------------------------------------------
# 8. Entity for src_ip extracted
#    Per backend/app/ingest/entity_extractor.py:64-70, network.connection
#    extracts only host + src_ip as entities (dst_ip is NOT an entity by
#    design — see ADR-0013 deferred items). Verify the source endpoint
#    is recorded; dst_ip still drives detection (asserted in step 9).
# ---------------------------------------------------------------------------
header "Entities: src_ip extracted"
HAS_SRC=$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U cybercat -d cybercat -t -A -c \
    "SELECT 1 FROM entities WHERE kind='ip' AND natural_key='10.0.0.5' LIMIT 1;" 2>/dev/null \
    | tr -d '[:space:]')
[ "$HAS_SRC" = "1" ] && pass "Entity 10.0.0.5 (src_ip) extracted from network.connection" \
    || { fail "src_ip 10.0.0.5 missing from entities table"; exit 1; }

# ---------------------------------------------------------------------------
# 9. py.blocked_observable_match detection fired on dst_ip
# ---------------------------------------------------------------------------
header "Detection: py.blocked_observable_match"
DET_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/detections?rule_id=py.blocked_observable_match&limit=20") \
    || { fail "GET /v1/detections failed"; exit 1; }
DET_COUNT=$(echo "$DET_RESP" | $PY -c '
import json, sys
data = json.load(sys.stdin)
items = data.get("items", data) if isinstance(data, dict) else data
print(len(items))
')
if [ "$DET_COUNT" -ge 1 ]; then
    pass "py.blocked_observable_match fired ($DET_COUNT row(s))"
else
    fail "py.blocked_observable_match did not fire"
    echo "DEBUG: detections response head:"
    echo "$DET_RESP" | head -c 800
    exit 1
fi

# Verify the matched_field/matched_value point at the dst_ip we blocked.
MATCHED_OK=$(echo "$DET_RESP" | $PY -c '
import json, sys
data = json.load(sys.stdin)
items = data.get("items", data) if isinstance(data, dict) else data
hit = False
for it in items:
    mf = it.get("matched_fields") or {}
    if mf.get("matched_field") == "dst_ip" and mf.get("matched_value") == "203.0.113.42":
        hit = True
        break
print("yes" if hit else "no")
')
if [ "$MATCHED_OK" = "yes" ]; then
    pass "Detection matched on dst_ip=203.0.113.42 (loop closed)"
else
    fail "Detection fired but not on dst_ip=203.0.113.42"
    echo "$DET_RESP" | $PY -m json.tool 2>/dev/null | head -40
    exit 1
fi

# ---------------------------------------------------------------------------
# 10. Wazuh path stays dormant (no regression)
# ---------------------------------------------------------------------------
header "Wazuh dormant"
WZ_RESP=$(curl -sf "${AUTH_HEADER[@]}" "${API}/v1/wazuh/status") || true
WZ_STATUS=$(echo "$WZ_RESP" | $PY -c '
import json, sys
d = json.load(sys.stdin)
print(("disabled" if not d.get("enabled") else
       "unreachable" if not d.get("reachable") else "active"))
' 2>/dev/null || echo "?")
case "$WZ_STATUS" in
    disabled)    pass "Wazuh bridge disabled in config (no regression)" ;;
    unreachable) pass "Wazuh containers not running — bridge dormant (no regression)" ;;
    *)           fail "Wazuh path is unexpectedly active: $WZ_RESP" ;;
esac

# ---------------------------------------------------------------------------
# 11. Conntrack checkpoint advanced
# ---------------------------------------------------------------------------
header "Conntrack checkpoint"
CP_JSON=$(MSYS_NO_PATHCONV=1 docker exec compose-cct-agent-1 \
    cat /var/lib/cct-agent/conntrack-checkpoint.json 2>&1 || echo "MISSING")
if [ "$CP_JSON" = "MISSING" ] || ! echo "$CP_JSON" | grep -q "offset"; then
    fail "Conntrack checkpoint missing or malformed: $CP_JSON"
else
    OFFSET=$(echo "$CP_JSON" | $PY -c 'import json,sys; print(json.load(sys.stdin)["offset"])')
    if [ "$OFFSET" -gt 0 ]; then
        pass "Conntrack checkpoint advanced (offset=$OFFSET)"
    else
        fail "Conntrack checkpoint offset is 0 — agent has not advanced"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Phase 16.10 smoke test complete: ${GREEN}${PASSES} passed${RESET}, ${RED}${FAILURES} failed${RESET}"
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1
