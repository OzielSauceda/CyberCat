#!/usr/bin/env bash
# Phase 13 smoke test — Real-Time Streaming (SSE).
# Run from the repo root: bash labs/smoke_test_phase13.sh
# Requires: docker compose up -d (infra/compose/) and a running backend
set -euo pipefail

API="http://localhost:8000"
COMPOSE_FILE="infra/compose/docker-compose.yml"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
RESET='\033[0m'

[ -f "labs/.smoke-env" ] && source "labs/.smoke-env" || true
[ -n "${SMOKE_API_TOKEN:-}" ] && AUTH_HEADER=(-H "Authorization: Bearer $SMOKE_API_TOKEN") || AUTH_HEADER=()

pass()   { echo -e "${GREEN}PASS${RESET} $1"; PASSES=$((PASSES + 1)); }
fail()   { echo -e "${RED}FAIL${RESET} $1"; FAILURES=$((FAILURES + 1)); }
warn()   { echo -e "${YELLOW}WARN${RESET} $1"; }
header() { echo -e "\n${BOLD}--- $1 ---${RESET}"; }

PASSES=0
FAILURES=0
STREAM_PID=""

cleanup() {
    [ -n "$STREAM_PID" ] && kill "$STREAM_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 1. Backend healthcheck
# ---------------------------------------------------------------------------
header "Backend health"
http_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/healthz")
[ "$http_status" = "200" ] && pass "Backend is healthy" || { fail "Backend not healthy (HTTP $http_status)"; exit 1; }

# ---------------------------------------------------------------------------
# 2. SSE endpoint responds with text/event-stream
# ---------------------------------------------------------------------------
header "SSE content-type"
ct=$(curl -s "${AUTH_HEADER[@]}" -D- -o /dev/null --max-time 3 "${API}/v1/stream" 2>/dev/null | grep -i "content-type" | head -1 || true)
echo "$ct" | grep -qi "text/event-stream" \
    && pass "GET /v1/stream returns text/event-stream" \
    || fail "GET /v1/stream content-type wrong: $ct"

# ---------------------------------------------------------------------------
# 3. Heartbeat received within 25s
# ---------------------------------------------------------------------------
header "Heartbeat test"
HB_LOG=$(mktemp)
timeout 25 curl -s "${AUTH_HEADER[@]}" -N --max-time 25 "${API}/v1/stream" > "$HB_LOG" 2>/dev/null || true
grep -q ": hb" "$HB_LOG" \
    && pass "Heartbeat received within 25s" \
    || fail "No heartbeat in stream log"
rm -f "$HB_LOG"

# ---------------------------------------------------------------------------
# 4. Setup: truncate DB and flush Redis
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
# 5. Open SSE stream + run credential_theft_chain scenario
# ---------------------------------------------------------------------------
header "Scenario: credential_theft_chain → SSE events"
STREAM_LOG=$(mktemp)
curl -s "${AUTH_HEADER[@]}" -N "${API}/v1/stream" > "$STREAM_LOG" &
STREAM_PID=$!
sleep 1

# Trigger identity_compromise correlator via direct API calls
# (matches the pattern used in test_propose_action_emits_event:
#  2x auth.failed + 1x auth.succeeded for same user/source_ip)
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.failed","occurred_at":"2026-01-01T11:00:00Z","raw":{},"normalized":{"user":"smoke-scenario","source_ip":"5.5.5.5","auth_type":"password"},"dedupe_key":"smoke-scenario-af-1"}' > /dev/null
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.failed","occurred_at":"2026-01-01T11:00:30Z","raw":{},"normalized":{"user":"smoke-scenario","source_ip":"5.5.5.5","auth_type":"password"},"dedupe_key":"smoke-scenario-af-2"}' > /dev/null
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.succeeded","occurred_at":"2026-01-01T11:01:00Z","raw":{},"normalized":{"user":"smoke-scenario","source_ip":"5.5.5.5","auth_type":"password"},"dedupe_key":"smoke-scenario-as-1"}' > /dev/null

sleep 3
kill "$STREAM_PID" 2>/dev/null || true
STREAM_PID=""
sleep 0.5

# Assert events in log
grep -q "event: incident.created" "$STREAM_LOG" \
    && pass "incident.created event received" \
    || fail "No incident.created in stream log"

grep -q "event: detection.fired" "$STREAM_LOG" \
    && pass "detection.fired event received" \
    || fail "No detection.fired in stream log"

rm -f "$STREAM_LOG"

# ---------------------------------------------------------------------------
# 6. Topic filter test — actions topic should not receive incident.* events
# ---------------------------------------------------------------------------
header "Topic filter test"
FILTER_LOG=$(mktemp)
curl -s "${AUTH_HEADER[@]}" -N "${API}/v1/stream?topics=actions" > "$FILTER_LOG" &
FILTER_PID=$!
sleep 0.5

# Publish an incident-related event via ingest (single-event format)
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.failed","occurred_at":"2026-01-01T12:00:00Z","raw":{},"normalized":{"user":"smoke-topic-test","source_ip":"9.9.9.9","auth_type":"password"},"dedupe_key":"smoke-topic-filter-1"}' > /dev/null

sleep 2
kill "$FILTER_PID" 2>/dev/null || true
sleep 0.3

if grep -q "event: incident\." "$FILTER_LOG"; then
    fail "Topic filter leaked incident.* events to ?topics=actions consumer"
else
    pass "Topic filter correctly blocked incident.* events"
fi
rm -f "$FILTER_LOG"

# ---------------------------------------------------------------------------
# 7. Invalid topic returns HTTP 400
# ---------------------------------------------------------------------------
header "Invalid topic rejection"
bad_status=$(curl -s "${AUTH_HEADER[@]}" -o /dev/null -w "%{http_code}" "${API}/v1/stream?topics=not_a_topic")
[ "$bad_status" = "400" ] \
    && pass "Invalid topic returns HTTP 400" \
    || fail "Expected 400, got $bad_status"

# ---------------------------------------------------------------------------
# 8. Multi-client fan-out
# ---------------------------------------------------------------------------
header "Multi-client fan-out"
LOG1=$(mktemp)
LOG2=$(mktemp)
curl -s "${AUTH_HEADER[@]}" -N "${API}/v1/stream?topics=detections" > "$LOG1" &
PID1=$!
curl -s "${AUTH_HEADER[@]}" -N "${API}/v1/stream?topics=detections" > "$LOG2" &
PID2=$!
sleep 0.5

# Trigger detection.fired via ingest — needs the 3-event pattern (single auth.failed
# alone doesn't fire any detection rule; auth_anomalous_source_success fires on auth.succeeded)
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.failed","occurred_at":"2026-01-01T13:00:00Z","raw":{},"normalized":{"user":"fanout-user","source_ip":"1.2.3.5","auth_type":"password"},"dedupe_key":"smoke-fanout-af-1"}' > /dev/null
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.failed","occurred_at":"2026-01-01T13:00:30Z","raw":{},"normalized":{"user":"fanout-user","source_ip":"1.2.3.5","auth_type":"password"},"dedupe_key":"smoke-fanout-af-2"}' > /dev/null
curl -s "${AUTH_HEADER[@]}" -X POST "${API}/v1/events/raw" \
    -H "Content-Type: application/json" \
    -d '{"source":"direct","kind":"auth.succeeded","occurred_at":"2026-01-01T13:01:00Z","raw":{},"normalized":{"user":"fanout-user","source_ip":"1.2.3.5","auth_type":"password"},"dedupe_key":"smoke-fanout-as-1"}' > /dev/null

sleep 3
kill "$PID1" 2>/dev/null || true
kill "$PID2" 2>/dev/null || true
sleep 0.3

GOT1=false; GOT2=false
grep -q "detection.fired\|incident.created" "$LOG1" 2>/dev/null && GOT1=true || true
grep -q "detection.fired\|incident.created" "$LOG2" 2>/dev/null && GOT2=true || true

$GOT1 && $GOT2 \
    && pass "Both SSE clients received events (fan-out working)" \
    || fail "Fan-out failed — client1=$GOT1 client2=$GOT2"
rm -f "$LOG1" "$LOG2"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Phase 13 smoke test complete: ${GREEN}${PASSES} passed${RESET}, ${RED}${FAILURES} failed${RESET}"
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1
