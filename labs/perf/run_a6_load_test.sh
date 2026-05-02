#!/usr/bin/env bash
# Phase 19 §A6 acceptance: 1000/s × 60s load harness against /v1/events/raw.
# Pass: 0% drops at API (failed_5xx=0, transport_errors=0),
#       p95 < 500ms,
#       peak Postgres connection count < 25,
#       achieved rate >= 95% of target.
set -e

COMPOSE="docker compose -f infra/compose/docker-compose.yml"
HARNESS_LOG=/tmp/cct_a6_harness.log
PG_LOG=/tmp/cct_a6_pgconn.log
: > "$HARNESS_LOG"
: > "$PG_LOG"

echo "[$(date +%T)] Wiping demo data..."
curl -s -X DELETE http://localhost:8000/v1/admin/demo-data > /dev/null

echo "[$(date +%T)] Starting Postgres connection sampler (1Hz, db=cybercat)..."
(
  while true; do
    n=$(MSYS_NO_PATHCONV=1 $COMPOSE exec -T postgres psql -U cybercat -d cybercat -At -c \
      "SELECT count(*) FROM pg_stat_activity WHERE datname='cybercat';" 2>/dev/null | tr -d '\r')
    echo "$(date +%H:%M:%S) ${n:-?}" >> "$PG_LOG"
    sleep 1
  done
) &
SAMPLER_PID=$!

# Make sure we kill the sampler even if harness fails.
trap 'kill $SAMPLER_PID 2>/dev/null || true' EXIT

echo "[$(date +%T)] Starting harness: --rate 1000 --duration 60 (in backend container)..."
MSYS_NO_PATHCONV=1 $COMPOSE exec -T backend python labs/perf/load_harness.py \
  --base-url http://localhost:8000 --rate 1000 --duration 60 > "$HARNESS_LOG" 2>&1
echo "[$(date +%T)] Harness done."

# Stop sampler.
kill $SAMPLER_PID 2>/dev/null || true
wait $SAMPLER_PID 2>/dev/null || true

echo
echo "----- harness output -----"
cat "$HARNESS_LOG"
echo
echo "----- pg conn samples (last 15) -----"
tail -15 "$PG_LOG"
echo
peak=$(awk '{print $2}' "$PG_LOG" | grep -E '^[0-9]+$' | sort -nr | head -1)
echo "Peak Postgres connection count (db=cybercat): $peak"
echo "§A6 bar: < 25 → $([ -n "$peak" ] && [ "$peak" -lt 25 ] && echo PASS || echo FAIL)"
