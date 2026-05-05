#!/usr/bin/env bash
# labs/drills/run.sh — Phase 20 Workstream-B operator-drill orchestrator.
#
# Runs a Phase 20 scenario, then walks the operator through decision points
# (pauses with "Press Enter when done" between checkpoints unless --no-pause).
# After each pause, polls the API to verify the operator's response landed
# (status transitioned, action proposed, etc.) and prints a debrief at the end.
#
# Per docs/phase-20-plan.md §B1 scope discipline: CLI-only. No frontend
# changes. The frontend sees a normal incident (or, for current-platform-
# state-gap drills, no incident — the drill markdown explains why).
#
# Usage:
#     bash labs/drills/run.sh <scenario_name> [--speed 0.1] [--no-pause]
#                              [--api http://localhost:8000] [--token TOK]
#
# Reads the cct-agent token from infra/compose/.env unless --token overrides.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

# Defaults
SCENARIO=""
SPEED="0.1"
PAUSE=1
API="${CCT_API:-http://localhost:8000}"
TOKEN_OVERRIDE=""
WAIT_TIMEOUT_SEC=30
ENV_FILE="${REPO_ROOT}/infra/compose/.env"

# ----- arg parsing -----
while [ $# -gt 0 ]; do
    case "$1" in
        --speed) SPEED="$2"; shift 2 ;;
        --speed=*) SPEED="${1#--speed=}"; shift ;;
        --no-pause) PAUSE=0; shift ;;
        --api) API="$2"; shift 2 ;;
        --api=*) API="${1#--api=}"; shift ;;
        --token) TOKEN_OVERRIDE="$2"; shift 2 ;;
        --token=*) TOKEN_OVERRIDE="${1#--token=}"; shift ;;
        --timeout) WAIT_TIMEOUT_SEC="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 <scenario_name> [--speed N] [--no-pause] [--api URL] [--token TOK] [--timeout SEC]"
            echo "Available scenarios: lateral_movement_chain, crypto_mining_payload,"
            echo "                     webshell_drop, ransomware_staging, cloud_token_theft_lite"
            exit 0
            ;;
        --*)
            echo "Unknown flag: $1" >&2
            exit 2
            ;;
        *)
            if [ -z "$SCENARIO" ]; then
                SCENARIO="$1"
            else
                echo "Unexpected positional arg: $1" >&2
                exit 2
            fi
            shift
            ;;
    esac
done

if [ -z "$SCENARIO" ]; then
    echo "ERROR: scenario name required" >&2
    echo "  e.g. bash labs/drills/run.sh lateral_movement_chain --speed 0.1" >&2
    exit 2
fi

# ----- token -----
if [ -n "$TOKEN_OVERRIDE" ]; then
    TOKEN="$TOKEN_OVERRIDE"
elif [ -f "$ENV_FILE" ]; then
    TOKEN=$(grep '^CCT_AGENT_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r')
else
    TOKEN=""
fi

AUTH_HEADER=()
if [ -n "$TOKEN" ]; then
    AUTH_HEADER=(-H "Authorization: Bearer $TOKEN")
fi

# ----- helpers -----
banner() {
    echo
    echo "============================================================"
    echo "  $*"
    echo "============================================================"
}

step() {
    echo
    echo "▸ $*"
}

prompt_continue() {
    if [ "$PAUSE" -eq 1 ]; then
        echo
        echo "    [PAUSE] $*"
        read -r -p "    Press Enter when ready to continue... " _
    fi
}

# Returns 0 if backend is up; 1 otherwise.
healthz_ok() {
    curl -sf "${AUTH_HEADER[@]}" "${API}/healthz" >/dev/null 2>&1
}

# Find newest incident matching <kind>. Echoes incident UUID on stdout or
# empty string if none found within timeout. (Drops the opened_after filter
# because URL-encoding the ISO `+` offset is brittle in shell. The list is
# already sorted opened_at DESC, so the newest match is what we want.)
wait_for_incident_kind() {
    local kind="$1"
    local timeout="$2"
    local end_ts=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$end_ts" ]; do
        local id
        id=$(curl -sf "${AUTH_HEADER[@]}" \
            "${API}/v1/incidents?limit=20" 2>/dev/null \
            | python3 -c "
import json, sys
data = json.load(sys.stdin)
for inc in data.get('items', []):
    if inc.get('kind') == '$kind':
        print(inc['id']); break
" 2>/dev/null)
        if [ -n "$id" ]; then
            echo "$id"
            return 0
        fi
        sleep 1
    done
    echo ""
    return 1
}

incident_status() {
    local id="$1"
    curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents/${id}" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null
}

incident_action_kinds() {
    local id="$1"
    curl -sf "${AUTH_HEADER[@]}" "${API}/v1/incidents/${id}" 2>/dev/null \
        | python3 -c "
import json, sys
data = json.load(sys.stdin)
acts = data.get('actions') or []
for a in acts: print(a.get('kind',''))
" 2>/dev/null
}

# ----- preflight -----
banner "Phase 20 Drill — $SCENARIO"

if ! healthz_ok; then
    echo "ERROR: backend not reachable at ${API}/healthz" >&2
    echo "  Bring the stack up with: bash start.sh" >&2
    exit 1
fi

# ----- run scenario -----
START_ISO=$(date -u +"%Y-%m-%dT%H:%M:%S.000000+00:00")
START_EPOCH=$(date +%s)

step "Running scenario at speed=${SPEED}..."
docker compose -f "$REPO_ROOT/infra/compose/docker-compose.yml" exec -T backend \
    python -m labs.simulator --scenario "$SCENARIO" --speed "$SPEED" \
    --api http://localhost:8000 --token "$TOKEN" --no-verify

# ----- per-scenario decision-point flow -----
# Each scenario knows what incident kind to wait for and what to ask the
# operator at each pause. Default behavior is "wait briefly, report what
# we found, debrief."

INCIDENT_ID=""
EXPECTED_KIND=""

case "$SCENARIO" in
    lateral_movement_chain)
        EXPECTED_KIND="identity_compromise"
        ;;
    crypto_mining_payload|webshell_drop|ransomware_staging|cloud_token_theft_lite)
        # Current platform state: no incident expected (recorded gaps).
        EXPECTED_KIND=""
        ;;
    *)
        EXPECTED_KIND=""
        ;;
esac

if [ -n "$EXPECTED_KIND" ]; then
    step "Waiting up to ${WAIT_TIMEOUT_SEC}s for ${EXPECTED_KIND} incident..."
    INCIDENT_ID=$(wait_for_incident_kind "$EXPECTED_KIND" "$WAIT_TIMEOUT_SEC")
    if [ -n "$INCIDENT_ID" ]; then
        echo "    ✓ Incident formed: $INCIDENT_ID"
        echo "    URL: ${API}/v1/incidents/${INCIDENT_ID}  (or http://localhost:3000/incidents/${INCIDENT_ID} in the UI)"
    else
        echo "    ⚠ No ${EXPECTED_KIND} incident formed within ${WAIT_TIMEOUT_SEC}s."
        echo "    Either a Phase 22 detector closed the gap (good!) or the scenario didn't fire as planned."
    fi
else
    step "Current platform state: this scenario produces no incident (recorded gap)."
    echo "    The events ran. The detection-as-code regression test asserts what fires."
    echo "    Drill focus: review the events table + understand why no detector matched."
fi

# ----- decision points: only meaningful if we have an incident -----
if [ -n "$INCIDENT_ID" ]; then
    prompt_continue "Open the incident in the UI. Identify the pivot entity (user/host)."
    STATUS=$(incident_status "$INCIDENT_ID")
    echo "    Current status: ${STATUS}"

    prompt_continue "Transition the incident to 'triaged' (use the UI button or POST /v1/incidents/${INCIDENT_ID}/transitions)."
    STATUS=$(incident_status "$INCIDENT_ID")
    if [ "$STATUS" = "triaged" ] || [ "$STATUS" = "investigating" ] || [ "$STATUS" = "contained" ] || [ "$STATUS" = "resolved" ]; then
        echo "    ✓ Status is now: ${STATUS}"
    else
        echo "    ⚠ Status still: ${STATUS} (expected to be progressed beyond 'new')"
    fi

    prompt_continue "Propose a containment action (e.g., block_observable on the attacker IP)."
    ACTION_KINDS=$(incident_action_kinds "$INCIDENT_ID")
    if echo "$ACTION_KINDS" | grep -q "block_observable\|invalidate_lab_session\|quarantine_host_lab"; then
        echo "    ✓ Containment action(s) proposed:"
        echo "$ACTION_KINDS" | sed 's/^/        - /'
    else
        echo "    ⚠ No containment-class action proposed yet."
    fi
fi

# ----- debrief -----
banner "Debrief"

DRILL_MD="${SCRIPT_DIR}/${SCENARIO}.md"
if [ -f "$DRILL_MD" ]; then
    echo "  Drill markdown: ${DRILL_MD}"
    echo "  Re-read the 'Expected outcome' and 'What this teaches' sections to lock the lesson in."
fi

ELAPSED=$(( $(date +%s) - START_EPOCH ))
echo "  Total drill time: ${ELAPSED}s."
echo
echo "  Done."
