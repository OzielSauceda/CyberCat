#!/usr/bin/env bash
# Phase 19 §A6 acceptance — v2 setup:
#   - WAZUH_BRIDGE_ENABLED=false (no DNS thrash on agent profile)
#   - Harness runs in cct-agent (separate container, separate CPU)
#   - Targets http://backend:8000 over the compose network (real network hop)
#   - Postgres connection sampler @ 1Hz
#
# Pass: 0% drops at API (failed_5xx=0, transport_errors=0),
#       p95 < 500ms,
#       peak Postgres connection count < 25,
#       achieved rate >= 95% of target.
set -e

COMPOSE="docker compose -f infra/compose/docker-compose.yml"
HARNESS_LOG=/tmp/cct_a6v2_harness.log
PG_LOG=/tmp/cct_a6v2_pgconn.log
: > "$HARNESS_LOG"
: > "$PG_LOG"

echo "[$(date +%T)] Wiping demo data..."
curl -s -X DELETE http://localhost:8000/v1/admin/demo-data > /dev/null

# Make sure harness is freshly copied (the rebuild may have reset cct-agent)
docker cp labs/perf/load_harness.py compose-cct-agent-1:/tmp/load_harness.py

echo "[$(date +%T)] Starting Postgres conn sampler..."
(
  while true; do
    n=$(MSYS_NO_PATHCONV=1 $COMPOSE exec -T postgres psql -U cybercat -d cybercat -At -c \
      "SELECT count(*) FROM pg_stat_activity WHERE datname='cybercat';" 2>/dev/null | tr -d '\r')
    echo "$(date +%H:%M:%S) ${n:-?}" >> "$PG_LOG"
    sleep 1
  done
) &
SAMPLER_PID=$!
trap 'kill $SAMPLER_PID 2>/dev/null || true' EXIT

echo "[$(date +%T)] Running harness in cct-agent: --rate 1000 --duration 60 --base-url http://backend:8000 ..."
MSYS_NO_PATHCONV=1 $COMPOSE exec -T cct-agent python /tmp/load_harness.py \
  --base-url http://backend:8000 --rate 1000 --duration 60 > "$HARNESS_LOG" 2>&1

echo "[$(date +%T)] Harness done."
kill $SAMPLER_PID 2>/dev/null || true
wait $SAMPLER_PID 2>/dev/null || true

echo
echo "----- harness output -----"
cat "$HARNESS_LOG"
echo
echo "----- pg conn samples (entire run) -----"
cat "$PG_LOG"
echo
peak=$(awk '{print $2}' "$PG_LOG" | grep -E '^[0-9]+$' | sort -nr | head -1)
echo "Peak Postgres connection count (db=cybercat): $peak"
echo "§A6 bar (peak<25): $([ -n "$peak" ] && [ "$peak" -lt 25 ] && echo PASS || echo FAIL)"
