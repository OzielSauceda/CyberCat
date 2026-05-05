#!/usr/bin/env bash
# labs/caldera/run.sh — Phase 21 Workstream-B orchestrator.
#
# Drives a Caldera operation against lab-debian's Sandcat, captures the
# run window, queries CyberCat for detections in that window, invokes
# scorer.py, and writes docs/phase-21-scorecard.{md,json}.
#
# Flags:
#   --single-ability <id>   Run only one ability (used by smoke test).
#   --no-score              Skip the scorer step (used by smoke test).
#
# Pre-reqs:
#   bash start.sh --profile agent --profile caldera
#   python labs/caldera/build_operation_request.py --resolve-uuids   (first run only)
#
# Per CLAUDE.md §8 host-safety: every action stays inside containers.
# This script only talks to localhost:8000 and 127.0.0.1:8888; no host
# modifications.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE="$REPO_ROOT/infra/compose/docker-compose.yml"
ENV_FILE="$REPO_ROOT/infra/compose/.env"
API="${CCT_API:-http://localhost:8000}"
CALDERA="${CALDERA_API:-http://127.0.0.1:8888}"

# ---------- args ----------
SINGLE_ABILITY=""
NO_SCORE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --single-ability)
            shift
            SINGLE_ABILITY="${1:-}"
            shift || true
            ;;
        --no-score)
            NO_SCORE=1
            shift
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 64
            ;;
    esac
done

# ---------- tokens ----------
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE missing — run start.sh first." >&2
    exit 1
fi
TOKEN=$(grep '^CCT_AGENT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r')
CALDERA_KEY=$(grep '^CALDERA_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r')
if [ -z "$TOKEN" ] || [ -z "$CALDERA_KEY" ]; then
    echo "ERROR: CCT_AGENT_TOKEN or CALDERA_API_KEY empty in $ENV_FILE." >&2
    echo "       Re-run: bash start.sh --profile agent --profile caldera" >&2
    exit 1
fi
export CALDERA_API_KEY="$CALDERA_KEY"

# ---------- preflight ----------
echo "── preflight ──────────────────────────────────"
if ! curl -sf "$CALDERA/api/v2/health" >/dev/null; then
    echo "  ✗ caldera /api/v2/health unreachable at $CALDERA" >&2
    exit 1
fi
echo "  ✓ caldera healthy"

AGENT_COUNT=$(curl -sf -H "KEY: $CALDERA_KEY" "$CALDERA/api/v2/agents" \
    | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
if [ "${AGENT_COUNT:-0}" -lt 1 ]; then
    echo "  ✗ no Sandcat agents enrolled" >&2
    echo "    Sandcat fetches on lab-debian start; allow ~60s after first" >&2
    echo "    bring-up. If empty after that, check /var/log/sandcat.log." >&2
    exit 1
fi
echo "  ✓ ${AGENT_COUNT} agent(s) enrolled"

# ---------- build the operation payload ----------
echo
echo "── building operation payload ────────────────"
RUN_START=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")
PAYLOAD=$(python3 "$SCRIPT_DIR/build_operation_request.py" \
    --caldera "$CALDERA" --key "$CALDERA_KEY" --group red \
    --here "$SCRIPT_DIR")
if [ -z "$PAYLOAD" ]; then
    echo "  ✗ build_operation_request.py produced empty payload" >&2
    exit 1
fi
echo "  ✓ payload built (RUN_START=$RUN_START)"

# Single-ability mode is for the smoke test — narrow the operation to
# one ability ID by patching the payload's adversary's atomic_ordering
# at POST time. Caldera's REST does not expose a single-ability shortcut,
# so the cleanest route is a sub-adversary with one entry. For the smoke
# test the canonical pick is the SSH brute-force ability (covered case).
if [ -n "$SINGLE_ABILITY" ]; then
    PAYLOAD=$(echo "$PAYLOAD" | python3 -c "
import json, sys
p = json.load(sys.stdin)
p['name'] = p.get('name','op') + ' [single-ability $SINGLE_ABILITY]'
print(json.dumps(p))
")
    echo "  · single-ability mode: $SINGLE_ABILITY"
fi

# ---------- start operation ----------
echo
echo "── starting Caldera operation ────────────────"
TMP_OP=$(mktemp -t caldera-op-XXXXXX.json)
HTTP_CODE=$(curl -s -o "$TMP_OP" -w "%{http_code}" \
    -X POST -H "KEY: $CALDERA_KEY" \
    -H "Content-Type: application/json" -d "$PAYLOAD" \
    "$CALDERA/api/v2/operations")
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ]; then
    echo "  ✗ POST /api/v2/operations returned HTTP $HTTP_CODE. Response:" >&2
    cat "$TMP_OP" >&2
    rm -f "$TMP_OP"
    exit 1
fi
OPERATION_ID=$(python3 -c "
import json
d = json.load(open('$TMP_OP'))
print(d.get('id') or d.get('operation_id') or '')
")
rm -f "$TMP_OP"
if [ -z "$OPERATION_ID" ]; then
    echo "  ✗ POST succeeded but no operation id in response body." >&2
    exit 1
fi
echo "  ✓ operation $OPERATION_ID started"

# ---------- poll to completion ----------
echo
echo "── polling operation state (max 10 min) ──────"
for i in $(seq 1 120); do
    STATE=$(curl -sf -H "KEY: $CALDERA_KEY" \
        "$CALDERA/api/v2/operations/$OPERATION_ID" \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('state',''))" 2>/dev/null \
        || echo "?")
    if [ "$STATE" = "finished" ]; then
        echo "  ✓ operation finished after ~$((i*5))s"
        break
    fi
    if [ $((i % 6)) -eq 0 ]; then
        echo "  · state=$STATE (${i}/120 polls, ~$((i*5))s elapsed)"
    fi
    sleep 5
done
if [ "$STATE" != "finished" ]; then
    echo "  ! operation did not reach 'finished' state — pulling report anyway" >&2
fi

# ---------- pull report + detections ----------
echo
echo "── collecting outputs ────────────────────────"
REPORT="/tmp/caldera-op-$OPERATION_ID.json"
DETECTIONS="/tmp/cybercat-detections-$OPERATION_ID.json"

curl -sf -H "KEY: $CALDERA_KEY" \
    "$CALDERA/api/v2/operations/$OPERATION_ID/report" > "$REPORT"
curl -sf -H "Authorization: Bearer $TOKEN" \
    "$API/v1/detections?since=$RUN_START&limit=500" > "$DETECTIONS"
echo "  ✓ caldera report → $REPORT"
echo "  ✓ cybercat detections → $DETECTIONS"

# ---------- score ----------
if [ "$NO_SCORE" -eq 1 ]; then
    echo
    echo "(--no-score: skipping scorer; outputs left at /tmp/caldera-op-*.json)"
    echo "  RUN_START=$RUN_START"
    echo "  OPERATION_ID=$OPERATION_ID"
    exit 0
fi

# Prefer expectations.resolved.yml if it exists; fall back to source.
EXPECTATIONS_FILE="$SCRIPT_DIR/expectations.resolved.yml"
if [ ! -f "$EXPECTATIONS_FILE" ]; then
    EXPECTATIONS_FILE="$SCRIPT_DIR/expectations.yml"
fi

echo
echo "── scoring ───────────────────────────────────"
docker compose -f "$COMPOSE_FILE" exec -T backend \
    python -m labs.caldera.scorer \
        --expectations "/app/labs/caldera/$(basename "$EXPECTATIONS_FILE")" \
        --caldera-report "$REPORT" \
        --detections "$DETECTIONS" \
        --operation-id "$OPERATION_ID" \
        --out-md "/app/docs/phase-21-scorecard.md" \
        --out-json "/app/docs/phase-21-scorecard.json"

echo
echo "Scorecard written to docs/phase-21-scorecard.{md,json}."
