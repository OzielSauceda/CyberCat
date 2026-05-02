#!/usr/bin/env bash
# Phase 19 §A3 acceptance test: 100/s × 30s with `restart postgres` at t=10s.
# Pass: ≥95% accepted, transport_errors well below 1992 (the pre-fix number),
# recovery within 30s.
set -e

COMPOSE="docker compose -f infra/compose/docker-compose.yml"
LOG=/tmp/cct_pg_restart.log
: > "$LOG"

echo "[$(date +%T)] Wiping demo data..."
curl -s -X DELETE http://localhost:8000/v1/admin/demo-data > /dev/null

echo "[$(date +%T)] Starting load harness (100/s × 30s) inside backend container..."
MSYS_NO_PATHCONV=1 $COMPOSE exec -T backend python labs/perf/load_harness.py \
  --base-url http://localhost:8000 --rate 100 --duration 30 > "$LOG" 2>&1 &
HARNESS_PID=$!

echo "[$(date +%T)] Harness PID=$HARNESS_PID. Sleeping 10s before postgres restart..."
sleep 10

echo "[$(date +%T)] Restarting postgres..."
$COMPOSE restart postgres
echo "[$(date +%T)] Postgres restart issued. Waiting for harness to finish..."

wait $HARNESS_PID
echo "[$(date +%T)] Harness done."
echo "----- harness output ($LOG) -----"
cat "$LOG"
