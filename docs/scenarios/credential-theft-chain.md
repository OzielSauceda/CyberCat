# Scenario: credential_theft_chain

**Simulator name:** `credential_theft_chain`
**Duration:** ~4 min real-time (`--speed 1.0`), ~30s compressed (`--speed 0.1`)

## What it simulates

A five-stage credential theft followed by hands-on-keyboard endpoint activity:

| Stage | t+ | Events | CyberCat reaction |
|-------|----|--------|-------------------|
| 1. Brute force | 0s | 6× `auth.failed` (alice from 203.0.113.42) | `py.auth.failed_burst` fires at count=4 |
| 2. Successful login | 60s | `auth.succeeded` (alice from 203.0.113.42) | `py.auth.anomalous_source_success` → **identity_compromise** incident opens |
| 3. Session established | 75s | `session.started` (alice @ workstation-42) | `lab_sessions` row created |
| 4. Lateral execution | 180s | `process.created` (powershell.exe -enc ...) | `py.process.suspicious_child` → **identity_endpoint_chain** incident opens (cross-layer!) |
| 5. Post-exploit | 240–250s | `process.created` (net use) + `network.connection` (outbound :4444) | Chain incident gains supporting events |

## What it should produce

After completion:
- 1 × `identity_compromise` incident, severity `high`, linked to user `alice` and IP `203.0.113.42`
- 1 × `identity_endpoint_chain` incident, severity `critical` (auto-elevated), linked to `alice` @ `workstation-42`
- Auto-proposed actions on the chain incident: `tag_incident(cross-layer-chain)`, `request_evidence(process_list)`, `request_evidence(triage_log)`

## How to run

From the repo root with the core stack running (`docker compose up -d` from `infra/compose/`):

```bash
pip install httpx          # one-time
python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify
```

Re-running within the same hour is idempotent — the dedup keys prevent duplicate incidents.

## ATT&CK coverage

- T1110 / T1110.003 — Brute Force / Password Spraying
- T1078 — Valid Accounts
- T1059 / T1059.001 — Command and Scripting Interpreter / PowerShell
