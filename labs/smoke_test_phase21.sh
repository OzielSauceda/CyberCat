#!/usr/bin/env bash
# labs/smoke_test_phase21.sh — Phase 21 §D1 end-to-end smoke.
#
# Asserts (per docs/phase-21-plan.md §D.3):
#   T1. caldera service is healthy under --profile caldera.
#   T2. sandcat process is running in lab-debian.
#   T3. Caldera API sees ≥1 agent in the 'red' group.
#   T4. A single-ability run (T1110.001 brute-force) fires
#       py.auth.failed_burst — proves the loop closes end-to-end.
#   T5. Scorecard files (md + JSON) exist and are non-empty.
#
# Pre-reqs: bash start.sh --profile agent --profile caldera
#           AND build_operation_request.py --resolve-uuids has been run
#           at least once.
#
# Per CLAUDE.md §8 host-safety: this script only talks to localhost:8000
# and 127.0.0.1:8888; no host modifications.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$REPO_ROOT/infra/compose/docker-compose.yml"
ENV_FILE="$REPO_ROOT/infra/compose/.env"
API="${CCT_API:-http://localhost:8000}"
CALDERA="${CALDERA_API:-http://127.0.0.1:8888}"

# ---------- token + key ----------
TOKEN=""
CALDERA_KEY=""
if [ -f "$ENV_FILE" ]; then
    TOKEN=$(grep '^CCT_AGENT_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r')
    CALDERA_KEY=$(grep '^CALDERA_API_KEY=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r')
fi
AUTH_HEADER=()
if [ -n "$TOKEN" ]; then
    AUTH_HEADER=(-H "Authorization: Bearer $TOKEN")
fi

PASS_COUNT=0
FAIL_COUNT=0

pass() { echo "  ✓ $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "  ✗ $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
header() { echo; echo "── $* ─────────────────────────────────────────"; }

# ---------- preflight ----------

if [ -z "$TOKEN" ]; then
    fail "CCT_AGENT_TOKEN missing in $ENV_FILE — re-run start.sh --profile agent --profile caldera"
    exit 1
fi
if [ -z "$CALDERA_KEY" ]; then
    fail "CALDERA_API_KEY missing in $ENV_FILE — re-run start.sh --profile agent --profile caldera"
    exit 1
fi
if ! curl -sf "${AUTH_HEADER[@]}" "$API/healthz" > /dev/null; then
    fail "backend not reachable at $API/healthz"
    exit 1
fi

# ---------- T1: caldera healthy ----------

header "T1 — caldera service healthy"
# Caldera 4.2.0 has no /api/v2/health (5.x only); /enter is a public
# route that 302-redirects unauthenticated requests, which curl -sf
# accepts (only 4xx/5xx fail).
if curl -sf "$CALDERA/enter" >/dev/null; then
    pass "caldera /enter → 302"
else
    fail "caldera /enter unreachable at $CALDERA"
fi

# ---------- T2: sandcat agent has beaconed ----------

header "T2 — sandcat agent has beaconed in lab-debian"
# The sandcat binary self-deletes after launch (a stealth feature of
# the gocat agent), so /opt/sandcat/sandcat is absent at steady state
# and `pgrep sandcat` won't match the process either. Asserting that
# /var/log/sandcat.log records a "Beacon (HTTP): ALIVE" line is the
# robust check — that's the agent telling us it has reached Caldera.
if docker compose -f "$COMPOSE_FILE" exec -T lab-debian \
        grep -q "Beacon.*ALIVE" //var/log/sandcat.log 2>/dev/null; then
    pass "sandcat beaconed at least once (Beacon ALIVE in /var/log/sandcat.log)"
else
    fail "no Beacon ALIVE line in /var/log/sandcat.log — Sandcat never reached Caldera"
fi

# ---------- T3: agent enrolled ----------

header "T3 — Caldera sees ≥1 enrolled agent"
AGENT_COUNT=$(curl -sf -H "KEY: $CALDERA_KEY" "$CALDERA/api/v2/agents" 2>/dev/null \
    | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null \
    || echo "0")
if [ "${AGENT_COUNT:-0}" -ge 1 ]; then
    pass "${AGENT_COUNT} agent(s) enrolled in Caldera"
else
    fail "no agents enrolled — Sandcat may need ≥60s after first bring-up"
fi

# ---------- T4: covered-ability loop closes ----------

header "T4 — covered ability fires expected detector"
RUN_START=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")

# Pick the sudo-brute-force-debian ability — Caldera 4.2.0's stockpile
# names this `sh:linux:sudo-brute-force-debian` (the SSH-specific
# ssh:linux:brute-force ability does not exist on the 4.2.0 line; we
# moved to the sudo variant in profile.yml during the Phase 21 4.2.0
# pin). It triggers PAM/auth.log failure events the same way sshd does,
# so py.auth.failed_burst is still the expected detector.
if bash "$SCRIPT_DIR/caldera/run.sh" --single-ability "STOCKPILE:sh:linux:sudo-brute-force-debian" --no-score \
        > "/tmp/phase21-smoke-T4.log" 2>&1; then
    sleep 5  # backend ingest + correlator window settle
    HITS=$(curl -sf "${AUTH_HEADER[@]}" \
        "$API/v1/detections?rule_id=py.auth.failed_burst&since=$RUN_START&limit=10" 2>/dev/null \
        | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('items',[])))" 2>/dev/null \
        || echo "0")
    if [ "${HITS:-0}" -ge 1 ]; then
        pass "covered ability triggered py.auth.failed_burst (${HITS} detections)"
    else
        fail "covered ability ran but py.auth.failed_burst did NOT fire (see /tmp/phase21-smoke-T4.log)"
    fi
else
    fail "labs/caldera/run.sh failed to drive a single-ability run (see /tmp/phase21-smoke-T4.log)"
fi

# ---------- T5: scorecard files generated ----------

header "T5 — scorecard files generated"
SCORECARD_MD="$REPO_ROOT/docs/phase-21-scorecard.md"
SCORECARD_JSON="$REPO_ROOT/docs/phase-21-scorecard.json"

# T5 expects a prior full run to have produced both files. If the smoke
# is run cold (no prior `bash labs/caldera/run.sh`), drive one full
# scorer pass now so the assertion is meaningful.
if [ ! -s "$SCORECARD_MD" ] || [ ! -s "$SCORECARD_JSON" ]; then
    echo "  · no scorecard yet — driving a full run to populate"
    bash "$SCRIPT_DIR/caldera/run.sh" > "/tmp/phase21-smoke-T5.log" 2>&1 || true
fi

if [ -s "$SCORECARD_MD" ] && [ -s "$SCORECARD_JSON" ]; then
    LINES=$(wc -l < "$SCORECARD_MD" | tr -d ' ')
    pass "docs/phase-21-scorecard.md (${LINES} lines) + .json present and non-empty"
else
    fail "scorecard files missing or empty (see /tmp/phase21-smoke-T5.log)"
fi

# ---------- summary ----------

echo
echo "═══════════════════════════════════════════════"
echo "  passed: $PASS_COUNT  failed: $FAIL_COUNT"
echo "═══════════════════════════════════════════════"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "Phase 21 smoke green."
    exit 0
else
    echo "Phase 21 smoke RED. Inspect /tmp/phase21-smoke-*.log."
    exit 1
fi
