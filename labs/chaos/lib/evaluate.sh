#!/usr/bin/env bash
# labs/chaos/lib/evaluate.sh — shared evaluation helpers for Phase 19.5 chaos scenarios.
#
# Every chaos scenario script under labs/chaos/scenarios/ sources this file
# and uses these helpers to compute the four §A1 acceptance counters in a
# consistent shape:
#
#   1. sim_tracebacks       — count "Traceback (most recent call last)" in the simulator's log.
#   2. backend_tracebacks   — same, in backend container logs from the chaos window.
#   3. event_count_5min     — count of rows in the events table from the last 5 minutes.
#   4. degraded_warnings    — count of degraded-mode log lines (pattern is scenario-specific).
#
# These counters match the shape that .github/workflows/chaos-redis.yml uses
# inline; once this helper lands, that workflow may optionally be tightened
# to source it (Phase 19.5 §B3 — non-breaking polish, not required for done).
#
# All functions:
#   - Print an integer to stdout (for capture via $(func ...)).
#   - Default to "0" on error so `set -uo pipefail` callers don't trip.
#   - Print no extra text on stdout; informational logs go to stderr.
#
# Usage from a scenario script:
#
#     SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
#     # shellcheck source=../lib/evaluate.sh
#     . "$SCRIPT_DIR/../lib/evaluate.sh"
#
#     # ... run the chaos ...
#
#     SIM_TB=$(count_traceback_lines sim.log)
#     BE_TB=$(count_traceback_lines backend.log)
#     EVT=$(count_postgres_events_5min)
#     DEG=$(count_degraded_warnings backend.log "redis_degraded|EventBus consumer crashed")
#     print_acceptance_summary "$SIM_TB" "$BE_TB" "$EVT" "$DEG"

# ----------------------------------------------------------------------------
# Constants — match infra/compose/docker-compose.yml
# ----------------------------------------------------------------------------
CHAOS_COMPOSE_FILE="${CHAOS_COMPOSE_FILE:-infra/compose/docker-compose.yml}"
CHAOS_COMPOSE_PROFILE="${CHAOS_COMPOSE_PROFILE:-agent}"
CHAOS_PG_USER="${CHAOS_PG_USER:-cybercat}"
CHAOS_PG_DB="${CHAOS_PG_DB:-cybercat}"

# ----------------------------------------------------------------------------
# count_traceback_lines <log_file>
#
# Counts unhandled Python tracebacks in <log_file>. Returns 0 if the file is
# missing — chaos can fail in ways where the log never gets written, and we
# want the eval to keep running and report that as "no tracebacks" + use the
# other counters to surface the actual failure.
# ----------------------------------------------------------------------------
count_traceback_lines() {
    local log_file="${1:-}"
    if [ -z "$log_file" ] || [ ! -f "$log_file" ]; then
        echo 0
        return 0
    fi
    # `grep -c` exits 1 on no matches; `|| true` handles that without
    # tripping `pipefail`. `tr -d` strips any stray whitespace.
    grep -c "Traceback (most recent call last)" "$log_file" 2>/dev/null \
        | tr -d ' \r\n' \
        || echo 0
}

# ----------------------------------------------------------------------------
# count_postgres_events_5min
#
# Returns the number of rows in the `events` table with occurred_at within
# the last 5 minutes. Runs psql inside the postgres container, so requires
# the stack to be up. Returns 0 if the query fails (e.g. postgres still
# recovering from chaos) — the calling scenario is responsible for waiting
# long enough that this count reflects steady state.
# ----------------------------------------------------------------------------
count_postgres_events_5min() {
    local count
    count=$(docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
        exec -T postgres psql -U "$CHAOS_PG_USER" -d "$CHAOS_PG_DB" -t -A \
        -c "SELECT count(*) FROM events WHERE occurred_at > now() - interval '5 minutes';" \
        2>/dev/null \
        | tr -d ' \r\n')
    if [ -z "$count" ] || ! printf '%s' "$count" | grep -qE '^[0-9]+$'; then
        echo 0
    else
        echo "$count"
    fi
}

# ----------------------------------------------------------------------------
# count_degraded_warnings <log_file> <pattern>
#
# Counts lines in <log_file> matching <pattern> (extended regex). Used to
# verify that the resilience layer actually fired — if this is 0, the chaos
# either didn't hit the right code path or got lucky timing, and the test
# should fail closed.
#
# Each scenario passes its own pattern. Examples:
#   A1: "redis_degraded|redis_state=unavailable|EventBus consumer crashed"
#   A2: "with_ingest_retry|connection_invalidated"
#   A4: "checkpoint advance|tail resumed"
# ----------------------------------------------------------------------------
count_degraded_warnings() {
    local log_file="${1:-}"
    local pattern="${2:-}"
    if [ -z "$log_file" ] || [ ! -f "$log_file" ] || [ -z "$pattern" ]; then
        echo 0
        return 0
    fi
    grep -cE "$pattern" "$log_file" 2>/dev/null \
        | tr -d ' \r\n' \
        || echo 0
}

# ----------------------------------------------------------------------------
# print_acceptance_summary <sim_tb> <be_tb> <event_count> <degraded>
#
# Prints the four-counter block in the same shape as chaos-redis.yml's
# inline evaluation. Sets exit status NOT in this function — the caller
# decides pass/fail and exits. This just prints.
# ----------------------------------------------------------------------------
print_acceptance_summary() {
    local sim_tb="${1:-?}"
    local be_tb="${2:-?}"
    local event_count="${3:-?}"
    local degraded="${4:-?}"

    echo "================================================================"
    echo "  §A1 acceptance evaluation"
    echo "================================================================"
    printf "  sim_tracebacks     = %s  (must be 0)\n" "$sim_tb"
    printf "  backend_tracebacks = %s  (must be 0)\n" "$be_tb"
    printf "  event_count_5min   = %s  (must be > 0)\n" "$event_count"
    printf "  degraded_warnings  = %s  (must be > 0)\n" "$degraded"
    echo "================================================================"
}

# ----------------------------------------------------------------------------
# capture_backend_log <output_file> [tail_lines]
#
# Writes the last N lines of the backend container's logs to <output_file>.
# Default tail is 250 lines (matches chaos-redis.yml). Always returns 0 even
# if docker compose fails — the caller checks the file's contents.
# ----------------------------------------------------------------------------
capture_backend_log() {
    local out_file="${1:-backend.log}"
    local tail_lines="${2:-250}"
    docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
        logs backend --tail "$tail_lines" \
        > "$out_file" 2>&1 \
        || true
}

# ----------------------------------------------------------------------------
# capture_agent_log <output_file> [tail_lines]
#
# Same as capture_backend_log but for the cct-agent container. Used by
# scenarios that exercise agent resilience (A3 partition, A4 SIGSTOP).
# ----------------------------------------------------------------------------
capture_agent_log() {
    local out_file="${1:-agent.log}"
    local tail_lines="${2:-250}"
    docker compose -f "$CHAOS_COMPOSE_FILE" --profile "$CHAOS_COMPOSE_PROFILE" \
        logs cct-agent --tail "$tail_lines" \
        > "$out_file" 2>&1 \
        || true
}

# ----------------------------------------------------------------------------
# cleanup_chaos_state
#
# Best-effort defensive teardown. Called from a trap on EXIT in every
# scenario script so the stack returns to a usable state even on script
# failure or Ctrl-C. Each cleanup is wrapped in `|| true` because some
# operations are no-ops depending on which scenario ran.
#
# What it does:
#   - Removes any leftover tc qdisc inside the postgres container (A6).
#   - Reconnects cct-agent to the compose default network (A3).
#   - Unpauses cct-agent (A4).
#   - Restarts redis if it's missing (A1).
#   - Restarts backend if it's missing (A5).
#
# Note: this does NOT bring the stack down — the operator runs `start.sh`,
# the chaos scenario runs, this cleanup leaves the stack in the post-chaos
# state, and the operator chooses when to `docker compose down`.
# ----------------------------------------------------------------------------
cleanup_chaos_state() {
    local cf="$CHAOS_COMPOSE_FILE"
    local pf="$CHAOS_COMPOSE_PROFILE"

    # A6: tc qdisc cleanup. Best-effort; if no qdisc exists, tc returns 2.
    docker compose -f "$cf" --profile "$pf" exec -T postgres \
        tc qdisc del dev eth0 root 2>/dev/null || true

    # A3: ensure cct-agent is reconnected to the default compose network.
    # Auto-detect the network name from `docker network ls`.
    local net
    net=$(docker network ls --format '{{.Name}}' | grep -E 'compose_default$|cybercat_default$' | head -1 || true)
    if [ -n "$net" ]; then
        # `docker network connect` returns 1 if already connected; that's fine.
        docker network connect "$net" compose-cct-agent-1 2>/dev/null || true
    fi

    # A4: unpause cct-agent if paused. `docker compose unpause` is idempotent
    # for not-paused containers (returns 0).
    docker compose -f "$cf" --profile "$pf" unpause cct-agent 2>/dev/null || true

    # A1: restart redis if it died.
    docker compose -f "$cf" --profile "$pf" up -d redis 2>/dev/null || true

    # A5: restart backend if it died.
    docker compose -f "$cf" --profile "$pf" up -d backend 2>/dev/null || true
}

# ----------------------------------------------------------------------------
# read_token_from_env
#
# Reads CCT_AGENT_TOKEN from infra/compose/.env. Used by scenarios that need
# to drive the simulator from the host (A1, A5, A6). Empty string if not
# present — caller decides whether that's fatal.
# ----------------------------------------------------------------------------
read_token_from_env() {
    local env_file="${CHAOS_ENV_FILE:-infra/compose/.env}"
    if [ ! -f "$env_file" ]; then
        echo ""
        return 0
    fi
    grep '^CCT_AGENT_TOKEN=' "$env_file" 2>/dev/null \
        | head -1 \
        | cut -d= -f2- \
        | tr -d '\r' \
        || echo ""
}
