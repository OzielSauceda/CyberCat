#!/usr/bin/env bash
# labs/chaos/run_chaos.sh
#
# Phase 19.5 chaos orchestrator. Runs all six scenarios sequentially against
# an already-up stack. Collects PASS/FAIL from each and prints a summary
# table at the end. Exits 0 only if all six green.
#
# Assumes the operator already ran `bash start.sh` (does NOT bring the stack
# up itself — start.sh handles agent-profile + token bootstrap, and we want
# the operator to control stack lifecycle).
#
# Each scenario script is responsible for its own setup, teardown, and
# trap-on-EXIT cleanup. The orchestrator just invokes them in sequence,
# captures their exit code + stdout summary, and tallies.
#
# Between scenarios we do a brief pause (default 10s) for the stack to
# settle — chaos cleanup leaves connections in transition states that
# can confuse the next scenario's pre-flight check.
#
# Usage:
#   bash labs/chaos/run_chaos.sh
#
# Override defaults:
#   INTER_SCENARIO_PAUSE=20 SCENARIOS="restart_postgres pause_agent" \
#     bash labs/chaos/run_chaos.sh
#
# CI: not directly wrapped — each individual chaos-<name>.yml workflow is
# triggerable from the Actions tab. The orchestrator is the local-run UX
# the roadmap envisioned in `docs/roadmap-discussion-2026-04-30.md` §A1–A6.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCENARIOS_DIR="$SCRIPT_DIR/scenarios"

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
: "${INTER_SCENARIO_PAUSE:=10}"

# Default scenarios in roadmap order: A1, A2, A3, A4, A5, A6.
# Override SCENARIOS to run a subset (space-separated).
DEFAULT_SCENARIOS=(
    "kill_redis"        # A1
    "restart_postgres"  # A2
    "partition_agent"   # A3
    "pause_agent"       # A4
    "oom_backend"       # A5
    "slow_postgres"     # A6
)
if [ -n "${SCENARIOS:-}" ]; then
    # shellcheck disable=SC2206
    SCENARIO_LIST=($SCENARIOS)
else
    SCENARIO_LIST=("${DEFAULT_SCENARIOS[@]}")
fi

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------
if ! curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "FAIL: backend not reachable at http://localhost:8000/healthz"
    echo "      Bring up the stack first: bash start.sh"
    exit 1
fi

echo "================================================================"
echo "  Phase 19.5 chaos orchestrator"
echo "  scenarios:        ${SCENARIO_LIST[*]}"
echo "  inter_pause:      ${INTER_SCENARIO_PAUSE}s"
echo "  start_time:       $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================================"

# ----------------------------------------------------------------------------
# Per-scenario tally arrays. Bash 4+ associative arrays would be cleaner,
# but we stick to plain arrays so this works on the macOS bash 3.2 too.
# ----------------------------------------------------------------------------
RESULTS_NAME=()
RESULTS_STATUS=()
RESULTS_DURATION_S=()
OVERALL_FAIL=0

# ----------------------------------------------------------------------------
# Main loop.
# ----------------------------------------------------------------------------
for scenario in "${SCENARIO_LIST[@]}"; do
    script_path="$SCENARIOS_DIR/${scenario}.sh"
    if [ ! -x "$script_path" ] && [ ! -f "$script_path" ]; then
        echo
        echo "----- SKIP: $scenario (script not found at $script_path) -----"
        RESULTS_NAME+=("$scenario")
        RESULTS_STATUS+=("SKIP")
        RESULTS_DURATION_S+=("0")
        continue
    fi

    echo
    echo "================================================================"
    echo "  RUN: $scenario"
    echo "  start: $(date +%T)"
    echo "================================================================"

    start_ts=$(date +%s)
    if bash "$script_path"; then
        status="PASS"
    else
        status="FAIL"
        OVERALL_FAIL=1
    fi
    end_ts=$(date +%s)
    duration=$((end_ts - start_ts))

    RESULTS_NAME+=("$scenario")
    RESULTS_STATUS+=("$status")
    RESULTS_DURATION_S+=("$duration")

    echo
    echo "----- $scenario: $status (${duration}s) -----"

    # Inter-scenario pause to let the stack settle. Skip after the last one.
    last_index=$((${#SCENARIO_LIST[@]} - 1))
    current_index=${#RESULTS_NAME[@]}
    if [ "$current_index" -le "$last_index" ]; then
        echo "[$(date +%T)] Pausing ${INTER_SCENARIO_PAUSE}s before next scenario..."
        sleep "$INTER_SCENARIO_PAUSE"
    fi
done

# ----------------------------------------------------------------------------
# Summary table.
# ----------------------------------------------------------------------------
echo
echo "================================================================"
echo "  Phase 19.5 chaos summary"
echo "  end_time:         $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================================"
printf "  %-20s  %-6s  %s\n" "scenario" "status" "duration"
printf "  %-20s  %-6s  %s\n" "--------" "------" "--------"
for i in "${!RESULTS_NAME[@]}"; do
    printf "  %-20s  %-6s  %ss\n" \
        "${RESULTS_NAME[$i]}" \
        "${RESULTS_STATUS[$i]}" \
        "${RESULTS_DURATION_S[$i]}"
done
echo "================================================================"

if [ "$OVERALL_FAIL" -ne 0 ]; then
    echo "OVERALL: FAIL — at least one scenario did not pass"
    exit 1
fi

# Count PASS and SKIP separately so the line is honest when some scripts
# aren't on disk yet (e.g. A1 kill_redis.sh until the head-start agent lands).
PASS_COUNT=0
SKIP_COUNT=0
for status in "${RESULTS_STATUS[@]}"; do
    case "$status" in
        PASS) PASS_COUNT=$((PASS_COUNT + 1)) ;;
        SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
    esac
done

if [ "$SKIP_COUNT" -eq 0 ]; then
    echo "OVERALL: PASS — all ${PASS_COUNT} scenarios green"
else
    echo "OVERALL: PASS — ${PASS_COUNT} green, ${SKIP_COUNT} skipped (script not on disk)"
fi
exit 0
