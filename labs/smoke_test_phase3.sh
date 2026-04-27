#!/usr/bin/env bash
# Phase 3 smoke test — identity_compromise scenario
# Run from repo root after: docker compose up -d (from infra/compose/)
# Usage: bash labs/smoke_test_phase3.sh

set -e
BASE="http://localhost:8000/v1"
T0=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "=== Phase 3 Smoke Test ==="
echo "Base URL: $BASE"
echo "t0: $T0"
echo ""

# Helper: POST a raw event and pretty-print the response
post_event() {
    local label="$1"
    local payload="$2"
    echo "--- $label ---"
    curl -s -X POST "$BASE/events/raw" \
        -H "Content-Type: application/json" \
        -d "$payload" | python3 -m json.tool
    echo ""
}

# 4x auth.failed
for i in 1 2 3 4; do
    post_event "auth.failed #$i" "{
        \"source\": \"seeder\",
        \"kind\": \"auth.failed\",
        \"occurred_at\": \"$T0\",
        \"raw\": {\"user\": \"alice@corp.local\", \"src_ip\": \"203.0.113.7\"},
        \"normalized\": {\"user\": \"alice@corp.local\", \"source_ip\": \"203.0.113.7\", \"auth_type\": \"basic\", \"reason\": \"bad_password\"}
    }"
    sleep 1
done

echo ">>> After 4th failure, detections_fired should be non-empty above."
echo ""

# 1x auth.succeeded
post_event "auth.succeeded" "{
    \"source\": \"seeder\",
    \"kind\": \"auth.succeeded\",
    \"occurred_at\": \"$T0\",
    \"raw\": {\"user\": \"alice@corp.local\", \"src_ip\": \"203.0.113.7\"},
    \"normalized\": {\"user\": \"alice@corp.local\", \"source_ip\": \"203.0.113.7\", \"auth_type\": \"basic\"}
}"

echo ">>> incident_touched should be non-null above."
echo ""

# Check incident list
echo "--- GET /v1/incidents ---"
curl -s "$BASE/incidents" | python3 -m json.tool
echo ""

echo "=== Done. Check output above for: ==="
echo "  - 4th auth.failed: detections_fired non-empty"
echo "  - auth.succeeded: detections_fired + incident_touched non-null"
echo "  - GET /incidents: 1 item with title containing 'alice@corp.local', severity=high"
