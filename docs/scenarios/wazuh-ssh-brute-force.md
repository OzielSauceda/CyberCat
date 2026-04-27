# Scenario: SSH Brute-Force via Wazuh + lab-debian

End-to-end recipe demonstrating Phase 8 — a real `identity_compromise` incident born from Wazuh telemetry. All steps run from the host shell via `docker compose exec`.

## Prerequisites

- Docker or Podman with compose plugin
- `WAZUH_INDEXER_PASSWORD` set in `.env` (or use the default `SecretPassword123!` for lab)
- `WAZUH_BRIDGE_ENABLED=true` in `.env`

## Steps

```bash
# 1. Bring up the Wazuh profile (includes lab-debian).
cd infra/compose
docker compose --profile wazuh up -d

# 2. Confirm the agent enrolled with the manager (~60–90 s after start).
docker compose --profile wazuh exec wazuh-manager /var/ossec/bin/agent_control -l
# → expect: lab-debian listed as Active.

# 3. Confirm CyberCat bridge is live.
curl -s http://localhost:8000/v1/wazuh/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('reachable:', d['reachable'])"
# → reachable: True

# 4. Fire the brute-force chain from inside lab-debian
#    (so sshd sees the connection and Wazuh sees the log).
docker compose --profile wazuh exec lab-debian bash -c '
  for i in 1 2 3 4; do
    sshpass -p wrong ssh -o StrictHostKeyChecking=no baduser@localhost true 2>/dev/null || true
  done
  sshpass -p lab123 ssh -o StrictHostKeyChecking=no realuser@localhost true
'
# → Four authentication_failed + one authentication_success emitted within seconds.

# 5. Watch the incident appear (~10 s).
sleep 10
curl -s "http://localhost:8000/v1/incidents?kind=identity_compromise" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; print(items[0]['title'] if items else 'none')"
# → Identity compromise: realuser (or similar)
```

## Expected results in the UI (http://localhost:3000/incidents)

- `identity_compromise` incident at severity `high`
- Events tagged `source=wazuh` visible in the timeline
- Raw Wazuh alert JSON (including `rule.id`, `rule.groups`, `agent.name=lab-debian`) visible when the event row is expanded
- `T1110` (Brute Force) ATT&CK tag rendered if present in the Phase 6 catalog
- Wazuh bridge badge in top-nav shows green "Wazuh · live"

## Fallback (no agent — CI or agent not enrolled)

Directly inject a fixture alert into the Wazuh Indexer to exercise the pull → decode → correlate path:

```bash
DATE=$(date -u +%Y.%m.%d)
PASS="${WAZUH_INDEXER_PASSWORD:-SecretPassword123!}"

curl -sk -u "admin:${PASS}" \
  -X POST "https://localhost:9200/wazuh-alerts-${DATE}/_doc" \
  -H "Content-Type: application/json" \
  -d @labs/fixtures/wazuh-sshd-fail.json
```

Wait 10 s, then check `GET /v1/events?source=wazuh`.

## Resilience test

```bash
# Stop the indexer — badge should go amber within 3 × poll_interval seconds
docker compose --profile wazuh stop wazuh-indexer
sleep 20
curl -s http://localhost:8000/v1/wazuh/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('reachable:', d['reachable'], '| error:', d['last_error'])"
# → reachable: False | error: <connection refused message>

# Restart — badge returns green without backend restart
docker compose --profile wazuh start wazuh-indexer
sleep 30
curl -s http://localhost:8000/v1/wazuh/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('reachable:', d['reachable'])"
# → reachable: True
```
