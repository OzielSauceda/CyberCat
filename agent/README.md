# cct-agent — CyberCat custom telemetry agent

A small Python 3.12 agent that tails `/var/log/auth.log`, parses sshd events into
the CyberCat canonical normalized event shape, and POSTs them to the backend's
`/v1/events/raw` endpoint with a Bearer token.

This is the **default** telemetry source for CyberCat as of Phase 16. The Wazuh
stack remains available behind `--profile wazuh`. See
[`docs/decisions/ADR-0011-direct-agent-telemetry.md`](../docs/decisions/ADR-0011-direct-agent-telemetry.md)
for the architectural rationale.

## v1 event scope

Four sshd event kinds, all parsed from `/var/log/auth.log`:

| Kind | sshd line example |
|---|---|
| `auth.failed` | `Failed password for invalid user baduser from 203.0.113.42 port 49852 ssh2` |
| `auth.succeeded` | `Accepted password for realuser from 10.0.0.50 port 49860 ssh2` |
| `session.started` | `pam_unix(sshd:session): session opened for user realuser by (uid=0)` |
| `session.ended` | `pam_unix(sshd:session): session closed for user realuser` |

These four are sufficient to drive `auth_failed_burst` and the
`identity_compromise` correlator end-to-end. Process and network events
(auditd, conntrack) are deferred to Phase 16.9+.

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `CCT_API_URL` | `http://backend:8000` | CyberCat backend base URL |
| `CCT_AGENT_TOKEN` | *(required)* | Bearer token for `/v1/events/raw` (analyst role) |
| `CCT_LOG_PATH` | `/var/log/auth.log` | sshd log file to tail |
| `CCT_CHECKPOINT_PATH` | `/var/lib/cct-agent/checkpoint.json` | Durable byte-offset state |
| `CCT_BATCH_SIZE` | `50` | Max events per HTTP flush |
| `CCT_FLUSH_INTERVAL_SECONDS` | `2.0` | Max seconds between HTTP flushes |

## Local development

```bash
cd agent
python -m venv .venv
.venv/Scripts/activate     # bash on Windows; use .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"

# Run tests
pytest

# Run the agent against a local backend (requires CCT_AGENT_TOKEN in env)
export CCT_AGENT_TOKEN=...   # from `python -m app.cli issue-token`
export CCT_API_URL=http://localhost:8000
export CCT_LOG_PATH=/tmp/auth.log
python -m cct_agent
```

## Deployment

The agent is built and run as part of the CyberCat compose stack. See
`infra/compose/docker-compose.yml` (`cct-agent` service) and
[`docs/runbook.md`](../docs/runbook.md) for operational details.
