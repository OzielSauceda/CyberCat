#!/usr/bin/env bash
# labs/chaos/scenarios/slow_postgres.sh
#
# Phase 19.5 scenario A6: inject 200ms network latency between backend and
# Postgres while the load harness fires events at a sustainable rate.
# Verifies that the explicit pool config (pool_size=20, max_overflow=10,
# pool_timeout=10, pool_pre_ping=True) handles sustained per-query latency
# without exhausting connections.
#
# Plan substitution: the original roadmap said "200ms latency on Postgres
# volume via tc" — but tc is for *network* packets, not disk I/O, and real
# disk-latency injection (dm-delay, blkdebug) requires CAP_SYS_ADMIN
# unavailable on ubuntu-latest. Redefined as 200ms network latency between
# backend and Postgres via `tc qdisc add dev eth0 root netem delay 200ms`
# in Postgres's network namespace. Tests the more realistic "slow Postgres
# connection" failure mode.
#
# Implementation note (deviation from the plan's "apt install iproute2"):
# the postgres image is `postgres:16-alpine` (Alpine uses apk, not apt) and
# the container lacks CAP_NET_ADMIN by default. Cleanest path is a
# short-lived `nicolaka/netshoot` sidecar with `--net container:<postgres>`
# + `--cap-add NET_ADMIN` — that injects the tc rule into postgres's
# network namespace WITHOUT modifying postgres's own cap set or compose
# config. The qdisc persists as long as postgres's net namespace exists.
# Cleanup uses the same sidecar pattern with `tc qdisc del`.
#
# Test recipe:
#   1. Truncate tables for a clean event window.
#   2. Add tc qdisc via netshoot sidecar (200ms delay on eth0).
#   3. Run load_harness at RATE/s × DURATION inside backend container.
#   4. Remove tc qdisc via netshoot sidecar.
#   5. Evaluate counters + harness JSON summary.
#
# Pass criteria:
#   - sim_tracebacks       == 0
#   - backend_tracebacks   == 0
#   - event_count_5min     > 0
#   - latency p99          < 5000 ms (the latency-bounded chaos test)
#   - harness achieved_rate ≥ 90% of target
#   - failed_5xx           == 0
#   - transport_errors     == 0
#
# Note on degraded_warnings: the standard backend doesn't log slow queries
# by default (no log_min_duration_statement enabled, no SQLAlchemy echo).
# For A6, latency p99 elevated above baseline IS the proof-of-chaos signal,
# so degraded_warnings is informational, not gating. (Other scenarios use
# explicit log lines emitted by the resilience layer — A6's resilience IS
# the connection pool, which doesn't log per-acquisition.)
#
# Usage (after `bash start.sh`):
#   bash labs/chaos/scenarios/slow_postgres.sh
#
# Override defaults via env vars:
#   RATE=30 DURATION=20 LATENCY_MS=500 \
#     bash labs/chaos/scenarios/slow_postgres.sh
#
# CI equivalent: .github/workflows/chaos-slow-postgres.yml

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
: "${RATE:=50}"                  # events/sec — lower than A2's 100/s because
                                  # every query now incurs +200ms; sustainable headroom
: "${DURATION:=30}"               # seconds
: "${LATENCY_MS:=200}"            # injected one-way latency on postgres eth0
: "${P99_THRESHOLD_MS:=5000}"     # plan §A6 acceptance: p99 detection latency < 5s
: "${NETSHOOT_IMAGE:=nicolaka/netshoot}"
: "${SCENARIO_NAME:=slow_postgres}"

# Defensive trap removes any leftover tc rule even on script failure.
# cleanup_chaos_state in lib/evaluate.sh does best-effort tc del via
# `docker compose exec postgres`, but that fails on this image (no
# iproute2). Override with a netshoot-based cleanup instead.
cleanup_a6() {
    if [ -n "${POSTGRES_CONTAINER:-}" ]; then
        docker run --rm \
            --net "container:${POSTGRES_CONTAINER}" \
            --cap-add NET_ADMIN \
            "$NETSHOOT_IMAGE" \
            tc qdisc del dev eth0 root 2>/dev/null \
            || true
    fi
    cleanup_chaos_state
}
trap 'cleanup_a6' EXIT

echo "================================================================"
echo "  chaos scenario A6: slow_postgres (${LATENCY_MS}ms tc netem on postgres eth0)"
echo "  rate=${RATE}/s  duration=${DURATION}s  p99_threshold=${P99_THRESHOLD_MS}ms"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pre-flight + auto-detect postgres container.
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable — bring up the stack with 'bash start.sh' first"
    exit 1
fi

POSTGRES_CONTAINER=$(docker ps --format '{{.Names}}' \
    | grep -E '(^|-|/)postgres(-1)?$' \
    | head -1 \
    || true)
if [ -z "$POSTGRES_CONTAINER" ]; then
    echo "FAIL: could not find postgres container"
    docker ps --format 'table {{.Names}}\t{{.Status}}'
    exit 1
fi
echo "[$(date +%T)] Detected postgres container: $POSTGRES_CONTAINER"

# Truncate event tables for a clean count window.
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -c "
        TRUNCATE evidence_requests, blocked_observables, lab_sessions,
                 notes, incident_transitions, action_logs, actions,
                 incident_attack, incident_entities, incident_events,
                 incident_detections, incidents, detections,
                 event_entities, events, entities
                 RESTART IDENTITY CASCADE;
    " > /dev/null 2>&1 || true
docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T redis redis-cli FLUSHDB > /dev/null 2>&1 || true

# ----------------------------------------------------------------------------
# Inject tc netem rule via netshoot sidecar.
# ----------------------------------------------------------------------------
echo "----- inject tc netem delay ${LATENCY_MS}ms on $POSTGRES_CONTAINER eth0 -----"
if ! docker run --rm \
        --net "container:${POSTGRES_CONTAINER}" \
        --cap-add NET_ADMIN \
        "$NETSHOOT_IMAGE" \
        tc qdisc add dev eth0 root netem delay "${LATENCY_MS}ms"; then
    echo "FAIL: could not add tc qdisc via netshoot sidecar — netshoot may be missing or docker doesn't support --net container:"
    exit 1
fi
echo "[$(date +%T)] tc rule active. Postgres queries from backend now see +${LATENCY_MS}ms RTT."

# ----------------------------------------------------------------------------
# Run load harness.
# ----------------------------------------------------------------------------
HARNESS_LOG="/tmp/cct_chaos_a6_harness.log"
: > "$HARNESS_LOG"

echo "[$(date +%T)] Starting load harness ${RATE}/s × ${DURATION}s under ${LATENCY_MS}ms postgres latency..."
MSYS_NO_PATHCONV=1 docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
    exec -T backend python labs/perf/load_harness.py \
    --base-url http://localhost:8000 --rate "$RATE" --duration "$DURATION" \
    > "$HARNESS_LOG" 2>&1 \
    || true

echo "[$(date +%T)] Harness done. Removing tc rule..."

# ----------------------------------------------------------------------------
# Remove tc rule (also handled by cleanup_a6 trap, but explicit is cleaner).
# ----------------------------------------------------------------------------
docker run --rm \
    --net "container:${POSTGRES_CONTAINER}" \
    --cap-add NET_ADMIN \
    "$NETSHOOT_IMAGE" \
    tc qdisc del dev eth0 root \
    || echo "WARN: tc qdisc del failed (may have already been removed)"

# ----------------------------------------------------------------------------
# Capture logs + evaluate.
# ----------------------------------------------------------------------------
BACKEND_LOG="/tmp/cct_chaos_a6_backend.log"
capture_backend_log "$BACKEND_LOG" 250

echo "================================================================"
echo "  load_harness output"
echo "================================================================"
cat "$HARNESS_LOG" || true
echo "================================================================"
echo "  backend logs (last 250 lines)"
echo "================================================================"
cat "$BACKEND_LOG" || true
echo "================================================================"

SIM_TB=$(count_traceback_lines "$HARNESS_LOG")
BE_TB=$(count_traceback_lines "$BACKEND_LOG")
EVT_COUNT=$(count_postgres_events_5min)

# A6 informational degraded pattern — slow query / connection pool warnings.
# Not gating; the latency proof is in the harness's p99 measurement.
DEGRADED=$(count_degraded_warnings "$BACKEND_LOG" \
    "QueuePool|pool_timeout|connection.*timeout|TimeoutError|slow query|statement_timeout")

# Pull harness summary fields. The harness emits one JSON object on stdout.
HARNESS_ACCEPTANCE=$(grep -E '"acceptance_passed":' "$HARNESS_LOG" \
    | head -1 \
    | grep -oE '(true|false)' \
    | head -1 \
    || echo "unknown")
: "${HARNESS_ACCEPTANCE:=unknown}"

# Extract p99 from the harness JSON. Fall back to "0" if missing/non-numeric.
P99_MS=$(grep -E '"p99":' "$HARNESS_LOG" \
    | head -1 \
    | grep -oE '[0-9]+(\.[0-9]+)?' \
    | head -1 \
    || echo "0")
: "${P99_MS:=0}"
# Round to integer for shell comparison.
P99_INT=${P99_MS%.*}
: "${P99_INT:=0}"

ACHIEVED_RATE=$(grep -E '"achieved_rate_per_sec":' "$HARNESS_LOG" \
    | head -1 \
    | grep -oE '[0-9]+(\.[0-9]+)?' \
    | head -1 \
    || echo "0")
: "${ACHIEVED_RATE:=0}"

FAILED_5XX=$(grep -E '"failed_5xx":' "$HARNESS_LOG" \
    | head -1 \
    | grep -oE '[0-9]+' \
    | head -1 \
    || echo "0")
: "${FAILED_5XX:=0}"

TRANSPORT_ERRORS=$(grep -E '"transport_errors":' "$HARNESS_LOG" \
    | head -1 \
    | grep -oE '[0-9]+' \
    | head -1 \
    || echo "0")
: "${TRANSPORT_ERRORS:=0}"

print_acceptance_summary "$SIM_TB" "$BE_TB" "$EVT_COUNT" "$DEGRADED"
echo "  A6 extras:"
printf "    p99_ms             = %s  (must be < %s)\n" "$P99_MS" "$P99_THRESHOLD_MS"
printf "    achieved_rate      = %s/s  (must be ≥ 90%% of target=%s)\n" "$ACHIEVED_RATE" "$RATE"
printf "    failed_5xx         = %s  (must be 0)\n" "$FAILED_5XX"
printf "    transport_errors   = %s  (must be 0)\n" "$TRANSPORT_ERRORS"
printf "    harness_accept     = %s\n" "$HARNESS_ACCEPTANCE"
echo "================================================================"

# ----------------------------------------------------------------------------
# Pass/fail decision.
# ----------------------------------------------------------------------------
FAIL=0
if [ "$SIM_TB" -gt 0 ]; then
    echo "FAIL: harness produced $SIM_TB traceback(s)"
    FAIL=1
fi
if [ "$BE_TB" -gt 0 ]; then
    echo "FAIL: backend produced $BE_TB traceback(s) under sustained Postgres latency"
    FAIL=1
fi
if [ "$EVT_COUNT" -le 0 ]; then
    echo "FAIL: 0 events in postgres last 5 min — ingest didn't survive the latency"
    FAIL=1
fi
if [ "$P99_INT" -ge "$P99_THRESHOLD_MS" ]; then
    echo "FAIL: p99 latency ${P99_MS}ms exceeds plan §A6 ceiling of ${P99_THRESHOLD_MS}ms"
    FAIL=1
fi
if [ "$FAILED_5XX" -gt 0 ]; then
    echo "FAIL: $FAILED_5XX failed_5xx responses — pool likely exhausted under sustained latency"
    FAIL=1
fi
if [ "$TRANSPORT_ERRORS" -gt 0 ]; then
    echo "FAIL: $TRANSPORT_ERRORS transport_errors — connection layer broke down"
    FAIL=1
fi

# achieved_rate ≥ 90% of target — use awk for float compare.
if ! awk -v achieved="$ACHIEVED_RATE" -v target="$RATE" \
    'BEGIN { exit !(achieved >= target * 0.90) }'; then
    echo "FAIL: achieved_rate ${ACHIEVED_RATE}/s below 90% of target ${RATE}/s"
    FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: §A6 acceptance NOT met"
    exit 1
fi

echo "PASS: §A6 acceptance met — sustained ${LATENCY_MS}ms postgres latency held at p99=${P99_MS}ms (<${P99_THRESHOLD_MS}ms), achieved_rate=${ACHIEVED_RATE}/s"
exit 0
