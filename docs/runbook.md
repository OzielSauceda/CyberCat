# Runbook — CyberCat

How to run, seed, demo, and test the platform locally. Entries marked **(TBI)** are still pending; everything else is implemented and verified.

---

## Prerequisites

- OS: Windows 11 (operator machine) with a POSIX shell (Git Bash for running scripts).
- Docker Desktop (Engine running before any `docker compose` commands).
- ~10 GB free disk for images + volumes.
- No local Python or Node install required — everything runs inside Docker.

## Repo layout (actual)

```
CyberCat/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routers/          # incidents, entities, events, detections,
│   │   │   │                     #   responses, attack, lab_assets, wazuh,
│   │   │   │                     #   evidence_requests, blocked_observables
│   │   │   └── schemas/          # pydantic response models + errors.py
│   │   ├── attack/               # catalog.json (37 entries) + catalog.py (ATT&CK v14.1)
│   │   ├── correlation/
│   │   │   ├── rules/            # identity_compromise, endpoint_compromise_join,
│   │   │   │                     #   endpoint_compromise_standalone
│   │   │   ├── auto_actions.py   # auto-proposes request_evidence on identity_compromise
│   │   │   └── extend.py
│   │   ├── detection/
│   │   │   ├── rules/            # auth_failed_burst, auth_anomalous_source_success,
│   │   │   │                     #   process_suspicious_child, blocked_observable
│   │   │   ├── sigma/            # parser.py, compiler.py, field_map.py,
│   │   │   │                     #   loader_registration.py
│   │   │   └── sigma_pack/       # pack.yml manifest + *.yml Sigma rules
│   │   ├── ingest/               # normalizer.py, entity_extractor.py, dedup.py,
│   │   │                         #   pipeline.py, wazuh_poller.py, wazuh_decoder.py
│   │   ├── response/
│   │   │   └── handlers/         # tag_incident, elevate_severity, flag_host_in_lab,
│   │   │                         #   quarantine_host, kill_process, invalidate_session,
│   │   │                         #   block_observable, request_evidence
│   │   └── db/                   # models.py, session.py, redis.py
│   ├── alembic/
│   │   └── versions/             # 0001–0008 (see "Database migrations" below)
│   ├── scripts/
│   │   └── dump_openapi.py       # writes backend/openapi.json
│   ├── tests/
│   │   ├── unit/                 # test_sigma_*, test_wazuh_decoder, test_handlers_real
│   │   └── integration/          # test_endpoint_standalone, test_sigma_fires,
│   │                             #   test_wazuh_poller, test_response_flow_phase9,
│   │                             #   test_blocked_observable_detection,
│   │                             #   test_evidence_request_auto_propose
│   ├── openapi.json              # committed OpenAPI snapshot (regenerate via dump_openapi.py)
│   └── pyproject.toml
├── frontend/
│   └── app/
│       ├── components/           # SeverityBadge, StatusPill, EntityChip, AttackTag,
│       │                         #   WazuhBridgeBadge, EvidenceRequestsPanel,
│       │                         #   BlockedObservablesBadge, ...
│       ├── lib/                  # api.ts, api.generated.ts, usePolling.ts,
│       │                         #   attackCatalog.ts, actionForms.ts
│       ├── actions/              # /actions top-level dashboard
│       ├── incidents/            # list page + [id]/ detail page
│       ├── entities/             # [id]/ detail page
│       ├── detections/           # filterable detections list
│       └── lab/                  # lab assets CRUD
├── labs/
│   ├── smoke_test_phase3.sh      # 5-check basic detection/correlation test
│   ├── smoke_test_phase5.sh      # 10-check interactive response test
│   ├── smoke_test_phase6.sh      # 15-check full identity→endpoint chain test
│   ├── smoke_test_phase7.sh      # 21-check Sigma + standalone endpoint test
│   ├── smoke_test_phase8.sh      # 27-check Wazuh bridge + decoder test
│   ├── smoke_test_phase9a.sh     # 14-check response handlers + blocked detection test
│   └── smoke_test_agent.sh       # 14-check agent identity-compromise demo (default profile)
├── infra/
│   └── compose/
│       └── docker-compose.yml
└── docs/
```

## Start the core stack

The default deployment runs the **custom telemetry agent** (`cct-agent`) as the source of sshd events. Wazuh is opt-in. See `docs/decisions/ADR-0011-direct-agent-telemetry.md` for the why.

```bash
# Project root — easiest path:
./start.sh                      # default: --profile agent (6 containers)
./start.sh --profile wazuh      # opt into Wazuh stack instead
./start.sh --profile agent --profile wazuh   # both — for "compare the sources" demos
```

Endpoints:
- Backend API: http://localhost:8000 (OpenAPI UI at `/docs`, health at `/healthz`)
- Frontend UI: http://localhost:3000

Stop everything:
```bash
./stop.sh
```

**Convenience scripts at project root:**
- `./start.sh [--profile <name>]` — auto-launches Docker Desktop if not running, brings the stack up, and on first run with `--profile agent` provisions the `cct-agent@local` user + an analyst-role API token (written into `infra/compose/.env` as `CCT_AGENT_TOKEN`). Repeatable: `--profile agent --profile wazuh` runs both.
- `./stop.sh` — wraps `docker compose down`. Use mid-session to free container memory without exiting your editor / Claude Code session. Containers come back fast on the next `./start.sh` because images stay cached.

**Important:** The frontend is a build image (no live volume mount). If you add new pages or modify frontend code, rebuild with:
```bash
docker compose build frontend && docker compose up -d frontend
```

The same applies to the agent — code in `agent/` is baked into the `compose-cct-agent` image at build time:
```bash
docker compose --profile agent build cct-agent && \
  docker compose --profile agent up -d --force-recreate cct-agent
```

## Telemetry sources (Phase 16)

CyberCat ships with a custom Python sidecar agent and supports Wazuh as an optional alternative. Both produce events for the same downstream pipeline (normalizer → detection → correlation → incidents).

### Two operational modes — pick one at startup, never mid-session

The agent and Wazuh paths are not picked per-incident; you choose at startup which one(s) to run. The action handlers gracefully degrade based on what's available, so the platform never errors when Wazuh is absent — it just does less in the real world.

| Mode | How to start | What works | What changes for response actions |
|---|---|---|---|
| **Observe-and-record (default)** | `./start.sh` | Full ingest + detection + correlation + incidents + UI + audit. Every analyst workflow is real. | "Quarantine host" / "Kill process" write the DB marker + audit log + SSE notification + UI update — but **no real `iptables -I INPUT DROP`** lands on the lab box. |
| **Observe-record-and-enforce** | `./start.sh --profile wazuh` + set `WAZUH_AR_ENABLED=true` in `.env` | Same as above, plus real OS-level enforcement. | Same UI button now also dispatches Wazuh Active Response → real iptables rule / real `kill -9` on the lab box. |

**When to pick which:**
- Day-to-day coding, demo recording, interview walk-through, the credential_theft_chain scenario → **default mode**. The detection logic and analyst experience are 100% real; only the OS-level enforcement is skipped.
- Specifically when you want to demonstrate "the platform actually changes the state of a real Linux box" → **Wazuh mode with AR enabled**. Use `iptables -L` inside lab-debian to show before/after.

**Why this is by design (not a limitation):** a system that silently switched between "real iptables" and "DB-only" mid-session would be unsafe — you'd never be sure if a click did anything. Startup-time configuration makes the behavior of every action button predictable from how the stack was started. Both modes are production-shape; one stops at the system-of-record, the other closes the loop to the host.

### Custom agent (`cct-agent`) — default

### Custom agent (`cct-agent`) — default ingest path

The agent lives in `agent/` and runs as a separate container under `--profile agent`. It tails `/var/log/auth.log` inside lab-debian via a shared read-only volume, parses sshd lines, and POSTs canonical events to `POST /v1/events/raw`. **The agent is telemetry-only** — it does not receive commands from the backend and cannot enforce OS-level response actions. That capability remains Wazuh-only via Active Response (see "Two operational modes" above).

**Event scope (Phase 16 + 16.9):** sshd source emits `auth.failed`, `auth.succeeded`, `session.started`, `session.ended`. **Auditd source (Phase 16.9)** emits `process.created` (every EXECVE) and `process.exited` (only for PIDs we previously saw start, via the bounded LRU in `agent/cct_agent/process_state.py`). Both sources run as independent asyncio tasks feeding a single shipper queue. Network events via conntrack are Phase 16.10.

**Configuration (env, all optional except CCT_AGENT_TOKEN):**

| Var | Default | Purpose |
|---|---|---|
| `CCT_API_URL` | `http://backend:8000` | Backend base URL |
| `CCT_AGENT_TOKEN` | *(provisioned by start.sh)* | Bearer token (analyst role) |
| `CCT_LOG_PATH` | `/lab/var/log/auth.log` | sshd log file (mounted from lab-debian) |
| `CCT_CHECKPOINT_PATH` | `/var/lib/cct-agent/checkpoint.json` | sshd byte-offset state |
| `CCT_AUDIT_LOG_PATH` | `/lab/var/log/audit/audit.log` | auditd log file (mounted from lab-debian) |
| `CCT_AUDIT_CHECKPOINT_PATH` | `/var/lib/cct-agent/audit-checkpoint.json` | auditd byte-offset state |
| `CCT_AUDIT_ENABLED` | `true` | Kill switch for the auditd source |
| `CCT_CONNTRACK_LOG_PATH` | `/lab/var/log/conntrack.log` | conntrack log file (mounted from lab-debian) |
| `CCT_CONNTRACK_CHECKPOINT_PATH` | `/var/lib/cct-agent/conntrack-checkpoint.json` | conntrack byte-offset state |
| `CCT_CONNTRACK_ENABLED` | `true` | Kill switch for the conntrack source |
| `CCT_HOST_NAME` | `lab-debian` | Logical host name for the events |
| `CCT_BATCH_SIZE` | `50` | Max events per HTTP flush |
| `CCT_FLUSH_INTERVAL_SECONDS` | `2.0` | Max seconds between HTTP flushes |

**First-run token bootstrap.** When `./start.sh --profile agent` runs and `CCT_AGENT_TOKEN` is empty in `infra/compose/.env`, the script:
1. Waits for the backend `/healthz` to return 200.
2. Runs `python -m app.cli create-user --email cct-agent@local --password <random> --role analyst` inside the backend container (idempotent — ignores "already exists").
3. Runs `python -m app.cli issue-token --email cct-agent@local --name cct-agent`, parses the printed token, and writes it into `.env`.
4. Recreates the `cct-agent` container so it picks up the new token.

This makes the first run zero-touch.

**Token rotation.** No automatic rotation in v1 (deferred to Phase 18). To rotate manually:

```bash
# 1. Issue a new token (the old one stays valid until you revoke it).
docker compose exec backend python -m app.cli issue-token \
  --email cct-agent@local --name cct-agent-rotated

# 2. Copy the printed token, replace the value in infra/compose/.env, restart the agent:
docker compose --profile agent up -d --force-recreate cct-agent

# 3. Optional: revoke the old token by ID (printed when you issued it).
docker compose exec backend python -m app.cli revoke-token --token-id <old-uuid>
```

**Troubleshooting the agent:**
- `docker logs compose-cct-agent-1 --tail 50` — should show `agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log + /lab/var/log/conntrack.log` shortly after startup (subset of paths when individual sources are disabled or unavailable), then per-source `... source started, tailing ...` lines, then `HTTP/1.1 201 Created` lines as events ship.
- HTTP 401 on every POST → `CCT_AGENT_TOKEN` is empty, expired, or revoked. Re-issue (above) and recreate the container.
- HTTP 422 in logs → backend rejected the payload as malformed. Inspect the agent log; the 4xx is logged with the offending event kind. Never retried.
- No events flowing despite valid log lines → check that lab-debian is up (`docker ps`) and that the shared volume contains data: `docker exec compose-cct-agent-1 ls -lh /lab/var/log/auth.log /lab/var/log/audit/audit.log /lab/var/log/conntrack.log`.
- Checkpoint inspection: `docker exec compose-cct-agent-1 cat /var/lib/cct-agent/checkpoint.json /var/lib/cct-agent/audit-checkpoint.json /var/lib/cct-agent/conntrack-checkpoint.json` — all three should show non-zero offsets advancing as events arrive on each source.
- "Replay everything" debug: `docker exec compose-cct-agent-1 rm /var/lib/cct-agent/checkpoint.json /var/lib/cct-agent/audit-checkpoint.json /var/lib/cct-agent/conntrack-checkpoint.json` then `docker compose --profile agent restart cct-agent`. The backend's dedup (`(source, dedupe_key)`) ensures replays don't duplicate events.

**Auditd source operations (Phase 16.9):**
- **Verify auditd is running inside lab-debian:** `docker exec compose-lab-debian-1 service auditd status` and `docker exec compose-lab-debian-1 auditctl -l` — the latter should list the `cybercat_exec` and `cybercat_exit` rules. If `auditctl` returns "Operation not permitted", the kernel audit netlink socket is unavailable to the container (common with Docker Desktop on Windows/macOS — the agent will log a warning and skip the audit source rather than crash). On Linux hosts, kernel audit usually Just Works with the `AUDIT_WRITE` + `AUDIT_CONTROL` capabilities the lab-debian service already requests.
- **Disable the audit source** (e.g. when running outside lab-debian): set `CCT_AUDIT_ENABLED=false` in `infra/compose/.env` and `docker compose --profile agent up -d --force-recreate cct-agent`. The agent will run sshd-only.
- **Inspect the audit checkpoint:** `docker exec compose-cct-agent-1 cat /var/lib/cct-agent/audit-checkpoint.json` — same `{inode, offset}` shape as the sshd checkpoint.
- **Common parse warnings:** lines that don't match the `type=... msg=audit(ts:id):` header are silently skipped (kernel records of non-tracked types like `LOGIN`, `USER_AUTH`, etc.). Buffered events that never receive an `EOE` record are flushed at the 100-line cap or on agent shutdown via `parser.flush()`.

**Conntrack source operations (Phase 16.10):**
- **Verify conntrack is running inside lab-debian:** `docker exec compose-lab-debian-1 pgrep -af conntrack` should list `conntrack -E -e NEW -o timestamp -o extended -o id`. The entrypoint spawns it under lab-debian's existing `NET_ADMIN` capability. To check it's emitting: `docker exec compose-lab-debian-1 bash -c 'curl -m 2 -s http://example.com >/dev/null; sleep 1; tail -3 /var/log/conntrack.log'` should show `[NEW]` lines.
- **Why `conntrack -E` may stay silent:** Docker Desktop on Windows / WSL2 does not expose the kernel's `nf_conntrack` netlink group to containers, so the subscription succeeds but no events arrive. The entrypoint wraps the spawn in `( ... ) || true` and the agent treats a missing `/var/log/conntrack.log` as "skip this source" rather than crashing. On Linux hosts the kernel netlink path Just Works.
- **Disable the conntrack source** (e.g. when running outside lab-debian, or to reduce event volume during a load test): set `CCT_CONNTRACK_ENABLED=false` in `infra/compose/.env` and `docker compose --profile agent up -d --force-recreate cct-agent`. The agent will run sshd + auditd only.
- **Inspect the conntrack checkpoint:** `docker exec compose-cct-agent-1 cat /var/lib/cct-agent/conntrack-checkpoint.json` — same `{inode, offset}` shape as the sshd and auditd checkpoints.
- **Common parser drops:** loopback (`127.0.0.0/8`, `::1`) and link-local (`169.254/16`, `fe80::/10`) records are dropped on purpose. `[UPDATE]` and `[DESTROY]` records are also dropped — only `[NEW]` becomes a `network.connection` event in v1. Protocols other than TCP/UDP/ICMP (e.g. `igmp`, `gre`) are silently dropped too.

**Smoke test:** `bash labs/smoke_test_agent.sh` — verifies the full path (5 SSH failures + 1 success → events → detection → identity_compromise incident → checkpoint persistence → restart-no-duplicates). Targets the agent stack; honours `SMOKE_API_TOKEN` from `labs/.smoke-env` if `AUTH_REQUIRED=true`.

### Switching to Wazuh

```bash
./stop.sh
./start.sh --profile wazuh
```

The detailed Wazuh bring-up (cert generation, security bootstrap, role mapping) is in the next section. Wazuh and the agent can both run concurrently if you want to compare the same scenario through both telemetry sources — note that no cross-source dedup exists in v1, so this will produce duplicate events.

## Add Wazuh (optional, heavier)

### Step 1 — Generate TLS certificates (one-time)

Wazuh-indexer 4.9.x aborts at boot if its TLS certs are not present. Run the cert generator **once** before the first bring-up (from `infra/compose/`):

```bash
docker compose -f wazuh-config/generate-indexer-certs.yml run --rm generator
```

This populates `wazuh-config/config/wazuh_indexer_ssl_certs/` with:
- `root-ca.pem` / `root-ca.key`
- `admin.pem` / `admin-key.pem`
- `wazuh-indexer.pem` / `wazuh-indexer-key.pem`
- `wazuh-manager.pem` / `wazuh-manager-key.pem`

The certs are bind-mounted into the indexer and manager containers by `docker-compose.yml`. Re-run the generator only if you wipe the `wazuh_indexer_data` volume (certs must stay in sync with the node identity stored in the volume).

**WSL2 note:** if the indexer OOM-kills on startup, run `wsl -u root sysctl -w vm.max_map_count=262144` before step 2.

### Step 2 — Set environment variables

These are already set in `infra/compose/.env`. Confirm or edit as needed:

```bash
WAZUH_BRIDGE_ENABLED=true
WAZUH_INDEXER_PASSWORD=SecretPassword123!   # must meet OpenSearch complexity requirements
LAB_REALUSER_PASSWORD=lab123                # password for realuser on lab-debian
WAZUH_REGISTRATION_PASSWORD=               # read from manager after first boot (see below)
```

### Step 3 — Bring up the Wazuh profile

```bash
docker compose --profile wazuh up -d
```

The indexer will come up but fail its healthcheck the first time — this is expected. The Wazuh indexer image does **not** auto-run `securityadmin.sh`, so the `.opendistro_security` index needs manual initialization (one-time per data-volume).

### Step 4 — One-time security bootstrap (first boot only)

Enter the indexer container:

```bash
docker compose exec wazuh-indexer bash
```

Inside the container (`bash-5.2$`), run these five short commands, one at a time:

```bash
cd /usr/share/wazuh-indexer
export OPENSEARCH_JAVA_HOME=$PWD/jdk
S=plugins/opensearch-security/tools/securityadmin.sh
R=certs/root-ca.pem; C=certs/admin.pem; K=certs/admin-key.pem
$S -cd opensearch-security/ -nhnv -cacert $R -cert $C -key $K -p 9200 -icl
```

You should see `Done with success` after ~5 seconds. Exit with `exit`.

The short-variable form is deliberate — terminals (WSL especially) wrap long pastes at ~150 chars and the line break turns into a newline that splits the command, causing bash to try to run the PEM files as scripts.

### Step 5 — Create `cybercat_reader` role + mapping (first boot only)

The `cybercat_reader` role must be created via the Security REST API after the cluster is up. This is a one-time step; the data persists in the `wazuh_indexer_data` volume.

```bash
# Create the read-only role
curl -sk -u 'admin:SecretPassword123!' \
  -X PUT 'https://localhost:9200/_plugins/_security/api/roles/cybercat_reader' \
  -H 'Content-Type: application/json' \
  -d '{
    "description": "Read-only access to wazuh-alerts-* for the CyberCat backend poller",
    "cluster_permissions": ["cluster:monitor/health","cluster:monitor/state","cluster:monitor/nodes/info"],
    "index_permissions": [{"index_patterns":["wazuh-alerts-*"],"allowed_actions":["read","search"]}]
  }'

# Map the user to the role
curl -sk -u 'admin:SecretPassword123!' \
  -X PUT 'https://localhost:9200/_plugins/_security/api/rolesmapping/cybercat_reader' \
  -H 'Content-Type: application/json' \
  -d '{"users":["cybercat_reader"]}'
```

Both should return `{"status":"CREATED",...}`.

**Why REST API, not securityadmin?** The indexer's `roles.yml` / `roles_mapping.yml` mount points see the image's default files (not our custom ones). Running `securityadmin.sh -cd` would upload the image defaults and overwrite config. REST API writes directly to the `.opendistro_security` index which survives restarts.

### Step 6 — Verify

```bash
# Indexer healthy?
curl -sk -u 'admin:SecretPassword123!' https://localhost:9200/_cluster/health

# cybercat_reader can search (expect 200)?
curl -sk -o /dev/null -w "%{http_code}" \
  -u 'cybercat_reader:CyberCatR3ader!' \
  'https://localhost:9200/wazuh-alerts-*/_search?size=1'

# cybercat_reader write blocked (expect 403)?
curl -sk -o /dev/null -w "%{http_code}" \
  -u 'cybercat_reader:CyberCatR3ader!' -X PUT \
  'https://localhost:9200/wazuh-alerts-test/_doc/1' \
  -H 'Content-Type: application/json' -d '{"test":"blocked"}'

# Agent enrolled?
MSYS_NO_PATHCONV=1 docker compose --profile wazuh exec wazuh-manager /var/ossec/bin/agent_control -l

# Bridge live (start backend with bridge on)?
curl -s http://localhost:8000/v1/wazuh/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('enabled:', d.get('enabled'), 'last_error:', d.get('last_error'))"
```

Expected: cluster health `green`; reader read=200, write=403; agent 001 `Active`; bridge `last_error: None`.

**Wazuh dashboard is deliberately not started** (see `docs/decisions/ADR-0004-wazuh-bridge.md §consequences`). CyberCat's UI is the analyst interface.

**Registration password:** on the first boot the manager auto-generates an enrollment password. Read it with:
```bash
docker compose --profile wazuh exec wazuh-manager cat /var/ossec/etc/authd.pass
```
Set it as `WAZUH_REGISTRATION_PASSWORD=<value>` in `.env` and restart `lab-debian` so it enrolls.

**Demo scenario:** see `docs/scenarios/wazuh-ssh-brute-force.md` for a step-by-step SSH brute-force drill.

Wazuh is resource-intensive (~2.8 GB RAM for manager + indexer). Stop during normal development:

```bash
docker compose --profile wazuh down
```

## Database migrations

Migrations run automatically on backend startup. To run manually:

```bash
# Inside the backend container:
docker compose exec backend alembic upgrade head

# Create a new migration (from host, via container):
docker compose exec backend alembic revision --autogenerate -m "message"
```

Current migrations:
- `0001_initial_schema` — all 14 tables, 16 enum types.
- `0002_add_classification_reason_and_tags` — `actions.classification_reason`, `incidents.tags`.
- `0003_preseed_lab_assets` — seeds alice@corp.local, lab-win10-01, 203.0.113.7.
- `0004_add_wazuh_cursor` — singleton cursor table for Wazuh poller state.
- `0005_response_state_tables` — `lab_sessions`, `blocked_observables`, `evidence_requests` tables + 3 PG enum types (`blockable_kind`, `evidence_kind`, `evidence_status`).
- `0006_phase11_action_result_partial` — adds `partial` value to `actionresult` and `actionstatus` PG enums (Phase 11).
- `0007_multi_operator_auth` — `users`, `api_tokens`, `actor_user_id` audit FKs, legacy sentinel backfill (Phase 14.1). Requires `citext` extension.
- `0008_add_incident_summary` — adds nullable `incidents.summary TEXT` for plain-language incident summaries (Phase 18). Old rows stay `NULL`; the frontend falls back to `incident.rationale` when `summary` is null.

## Plain-language copy (Phase 18)

User-facing strings flow through two centralized modules so the rest of the app never hardcodes a label:

- `frontend/app/lib/labels.ts` — single source of truth for enum-to-friendly-label maps. Each entry has shape `{ label, plain, slug? }` where `label` is the short visible label, `plain` is a one-sentence definition for tooltips, and `slug` (optional) is the glossary deep-link key. Covers `Severity`, `IncidentStatus`, `IncidentKind`, event kinds, role-in-incident, action classifications/statuses, evidence kinds, attack source, event source, detection rule source, plus an `ATTACK_TACTIC_GLOSS` table.
- `frontend/app/lib/glossary.ts` — long-form glossary entries (`title` / `short` / `long`) keyed by slug. Renders the canonical definitions in `/help` and powers `JargonTerm` tooltip pop-ups.
- `frontend/app/components/PlainTerm.tsx` — composite component implementing the hybrid pattern: plain primary label + small muted technical inline + hover tooltip with definition.

When adding a new enum value or a new event kind on the backend, add a matching entry to `labels.ts` and (if it's a domain term) a glossary entry. Don't render raw enum values in the UI.

**Backend incident `summary` field** — the correlator rules in `backend/app/correlation/rules/` write *both* `incident.rationale` (technical, kept for analyst depth and CLAUDE.md §2 explainability) and `incident.summary` (plain-language). The frontend leads with `summary` and shows `rationale` behind a "Show technical detail" expander. The recommendations engine (`backend/app/response/recommendations.py`) follows the same pattern with parallel `_RATIONALES` and `_SUMMARIES` template maps.

## Multi-operator auth (Phase 14)

### Bootstrap the first admin

Auth is **disabled by default** (`AUTH_REQUIRED=false`).  All existing demos and smoke scripts work without any auth setup.  To enable auth:

1. Set environment variables in `infra/compose/.env`:
   ```
   AUTH_REQUIRED=true
   AUTH_COOKIE_SECRET=<random-32-char-secret>   # e.g. openssl rand -hex 32
   ```
2. Restart the backend: `docker compose restart backend`
3. Seed the first admin user via the CLI:
   ```bash
   docker compose exec backend python -m app.cli seed-admin \
       --email admin@cybercat.local --password 'changeme'
   ```
4. Log in at `http://localhost:3000/login`.

### Create additional users

```bash
# Create an analyst
docker compose exec backend python -m app.cli create-user \
    --email analyst@example.com --password 'changeme' --role analyst

# Issue an API token for smoke scripts / CLI
docker compose exec backend python -m app.cli issue-token \
    --email analyst@example.com --name smoke-token
# Copy the printed token → store in labs/.smoke-env as SMOKE_API_TOKEN=cct_...
```

### OIDC opt-in setup

OIDC allows analysts to sign in via an existing identity provider (Google Workspace, Okta, Auth0, Keycloak, Authentik, etc.) without managing local passwords.  New SSO accounts are provisioned with `role=read_only`; an admin must elevate them.

#### 1. Register CyberCat with your provider

| Field | Value |
|---|---|
| Redirect URI | `http://localhost:8000/v1/auth/oidc/callback` (or your public URL) |
| Allowed scopes | `openid email profile` |
| Response type | `code` |
| Grant type | Authorization Code |

#### 2. Set environment variables

```bash
# in infra/compose/.env
OIDC_PROVIDER_URL=https://accounts.google.com          # Google example
# OIDC_PROVIDER_URL=https://dev-xxx.okta.com            # Okta example
# OIDC_PROVIDER_URL=https://your-keycloak/realms/master # Keycloak example
OIDC_CLIENT_ID=<your-client-id>
OIDC_CLIENT_SECRET=<your-client-secret>
OIDC_REDIRECT_URI=http://localhost:8000/v1/auth/oidc/callback
```

AUTH_REQUIRED must also be `true` for the session cookie to be set after SSO login.

#### 3. Restart the backend

```bash
docker compose restart backend
```

The backend fetches `{OIDC_PROVIDER_URL}/.well-known/openid-configuration` and the JWKS at startup.  Check `docker compose logs backend` for errors.

#### 4. Verify

1. Open `http://localhost:3000/login` — the **Sign in with SSO** button should appear.
2. Click it → redirected to your provider → sign in → redirected back → logged in as `read_only`.
3. Admin elevates the new account:
   ```bash
   docker compose exec backend python -m app.cli set-role \
       --email sso-user@example.com --role analyst
   ```
   Or via the API: `PATCH /v1/auth/users/{id}/role` with `{"role": "analyst"}` using an admin bearer token.

#### Troubleshooting OIDC

- **501 Not Implemented on `/v1/auth/oidc/login`** — `OIDC_PROVIDER_URL` is not set or the backend hasn't restarted.
- **Discovery failed at startup** — Check `docker compose logs backend` for `OIDC discovery failed`.  Most likely the provider URL is wrong or unreachable.
- **"State mismatch" in callback** — The 10-minute state cookie expired, or the user has cookies blocked.  Try again.
- **JIT user gets read_only but needs analyst** — Expected.  Admin runs `set-role` or `PATCH /auth/users/{id}/role`.
- **Email missing from ID token** — Some providers omit `email` from the ID token and put it in the userinfo endpoint.  CyberCat falls back to the userinfo endpoint automatically; ensure the `email` scope is requested.

---

## Running a Phase 11 enforcement demo

Phase 11 wires `quarantine_host_lab` and `kill_process_lab` to real Wazuh Active Response. Requires the Wazuh profile stack.

### Prerequisites

1. `.env` (in `infra/compose/`) must have:
   ```
   WAZUH_AR_ENABLED=true
   WAZUH_MANAGER_PASSWORD=<manager wui password>
   ```
2. Stack running: `docker compose -f infra/compose/docker-compose.yml --profile wazuh up -d`
3. Wait for lab-debian to enroll (~30s after startup): check `docker compose exec wazuh-manager /var/ossec/bin/agent_control -l` shows `lab-debian` Active.

### Run the smoke test

```bash
bash labs/smoke_test_phase11.sh
```

Checks:
- lab-debian enrolled in wazuh-manager
- quarantine_host_lab executes: `action.status=executed`, `ar_dispatch_status=dispatched`
- iptables DROP rule present on lab-debian
- kill_process_lab executes and process is gone
- AR metadata visible in action log `reversal_info`

### Cleanup

After the demo, flush the iptables rules added by quarantine:

```bash
bash labs/smoke_test_phase11.sh --cleanup
```

### Negative path (optional)

Stop the manager to verify the `partial` code path:

```bash
bash labs/smoke_test_phase11.sh --test-negative
```

Expected: `action.status=partial`, UI shows amber badge with "Action partially completed" tooltip.

### Verify AR commands were received

```bash
docker compose -f infra/compose/docker-compose.yml --profile wazuh \
    exec wazuh-manager tail /var/ossec/logs/active-responses.log
```

Should show dispatched commands with the correct agent_id.

---

## Running a demo scenario

The attack simulator fires a scripted multi-stage attack against the running stack and produces the full cross-layer incident narrative in the UI. No Wazuh required — it fires events directly via the backend API.

### Prerequisites

```bash
pip install httpx   # one-time; uses your local Python
```

### Run the flagship scenario

From the repo root with the core stack running (`docker compose up -d`):

```bash
# Compressed to ~30s (for testing/demos)
python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify

# Real-time (~4 min, for recording)
python -m labs.simulator --scenario credential_theft_chain --speed 1.0 --verify
```

**What to watch in the UI** while it runs:
1. After stage 2 (~60s real / ~6s compressed): a `identity_compromise` incident appears in the incident list.
2. After stage 4 (~180s real / ~18s compressed): a `identity_endpoint_chain` incident appears — severity already elevated to **critical** by the auto-action.
3. On the chain incident detail page: rationale references the prior identity incident; both `alice` and `workstation-42` are linked as entities; process list and triage log evidence requests are auto-proposed.

Re-running within the same hour is idempotent (dedup keys prevent duplicate incidents).

See `docs/scenarios/credential-theft-chain.md` for full stage-by-stage breakdown.

---

## Seed and verify (Phase 10 — current master test)

Run from the repo root with Git Bash:

```bash
bash labs/smoke_test_phase10.sh
```

This runs 15 checks: backend health, simulator exit code (built-in --verify passes), incident API assertions (identity_compromise + identity_endpoint_chain both present for alice, chain severity=critical, primary_host=workstation-42, rationale correct, entities linked), evidence_requests auto-proposed, idempotency (re-run adds no new incidents).

Prerequisite for phase 10 smoke test: `pip install httpx`

---

## Seed and verify (Phase 9A)

Run from the repo root with Git Bash:

```bash
bash labs/smoke_test_phase9a.sh
```

This runs 14 checks covering the new Phase 9A surface:
- Check 1: OpenAPI lists all 8 `action_kind` values (incl. new 5).
- Check 2: ATT&CK catalog has ≥37 entries.
- Check 3: Migration 0005 tables exist (`lab_sessions`, `blocked_observables`, `evidence_requests`).
- Check 4: `quarantine_host_lab` propose + execute → `notes` contains quarantine marker.
- Check 5: `kill_process_lab` execute → `evidence_requests` row auto-created (`kind=process_list`).
- Check 6: `invalidate_lab_session` execute + revert → `invalidated_at` set then cleared.
- Check 7: `block_observable` execute → `blocked_observables` row active.
- Check 8: Blocked IP in ingested event fires `py.blocked_observable_match` detection.
- Check 9: `request_evidence` execute → `evidence_requests` row `status=open`.
- Check 10: `identity_compromise` incident auto-proposes `triage_log` evidence request.
- Check 11: Evidence request collected (`status=collected`).
- Check 12: Evidence request dismissed (`status=dismissed`).
- Check 13: `block_observable` for out-of-scope asset returns 422 (scope guard).
- Check 14: Disruptive action revert returns 409.

Run the regression chain too:

```bash
bash labs/smoke_test_phase7.sh   # 21 checks
bash labs/smoke_test_phase8.sh   # 27 checks (requires --profile wazuh stack running)
```

## Run unit tests

```bash
docker compose -f infra/compose/docker-compose.yml exec backend python -m pytest tests/unit/ -v
```

Unit tests cover: Sigma parser, compiler, field map (38 tests) + Wazuh decoder (11 tests: sshd auth, auditd process, Sysmon EventID 1 process) + response handlers real (13 tests). No live DB or Redis needed for Sigma/decoder tests; handlers tests require the compose stack. Run the full suite with `pytest` (no path) from the container.

**Agent tests** (run from the host, not inside Docker): `cd agent && pytest` → **67 tests** (sshd parser 22, auditd parser 23, checkpoint 7, tail 7, shipper 8). No Docker required.

## Regenerate the OpenAPI snapshot

The backend writes `openapi.json` inside the container. Copy it to the host so the frontend codegen can read it:

```bash
# 1. Regenerate inside the container
docker compose -f infra/compose/docker-compose.yml exec backend python -m scripts.dump_openapi

# 2. Copy to host (required before npm run gen:api:file)
docker compose -f infra/compose/docker-compose.yml cp backend:/app/openapi.json backend/openapi.json
```

Then regenerate frontend types and verify:

```bash
cd frontend
npm run gen:api:file        # reads ../backend/openapi.json → writes app/lib/api.generated.ts
npm run typecheck           # tsc --noEmit — must exit 0
cd ..
```

Commit both `backend/openapi.json` and `frontend/app/lib/api.generated.ts` together whenever the API surface changes.

## Seed and verify the identity → endpoint chain (Phase 6 regression)

```bash
bash labs/smoke_test_phase6.sh
```

This is the Phase 6 regression test (15 checks). It:
1. Truncates the DB + flushes Redis for a clean start.
2. Posts 4× `auth.failed` + 1× `auth.succeeded` for `alice@corp.local` from `203.0.113.7`.
3. Verifies an incident is created (identity_compromise).
4. Posts 1× `process.created` (powershell.exe with `-EncodedCommand`) for alice on lab-win10-01.
5. Verifies the existing incident was extended (not a new one), now containing `py.process.suspicious_child`, the new process event, and `T1059.001` ATT&CK entry.
6. Verifies an `endpoint-activity-observed` auto-tag action was executed by the system.

All 15 checks must pass.

## Demo walkthrough (browser)

After running `smoke_test_phase9a.sh`:

**Identity → endpoint chain (high severity):**
1. Open `http://localhost:3000/incidents`. One `identity_compromise` at severity `high` and one `endpoint_compromise` at severity `medium` should appear.
2. Click the `identity_compromise` incident → detail page.
3. **Timeline panel** — 6 auth events + 1 process event, grouped by entity.
4. **Detections panel** — two detections on the process event: `rule_source=py` (`py.process.suspicious_child`) and `rule_source=sigma`. Both co-fired.
5. **Entities panel** — click alice's chip → routes to `/entities/<id>`. If alice's IP is blocked, a red **BLOCKED** badge appears next to the entity name.
6. **ATT&CK panel** — tags show names: `T1078 · Valid Accounts`, `T1059.001 · PowerShell`, etc. (37-entry catalog).
7. **Actions panel** — shows executed auto-tag actions (proposed_by=system) plus an auto-proposed `request_evidence` (suggest_only, proposed_by=system).
8. **Evidence Requests panel** — below Actions panel. Shows the auto-proposed `triage_log` evidence request (status=open). Click **Mark collected** → status turns green.

**Recommended response panel (Phase 15):**
8a. Above the **Response actions** panel on the incident detail page, the **Recommended response** panel renders 1–4 ranked, pre-filled action suggestions. Each row shows a classification badge, a humanized action label (e.g. "Block 203.0.113.42"), priority pill, rationale text, and an EntityChip for the target.
8b. Click **Use this** on the top recommendation → the **Propose action** modal opens with the kind already selected and the form fields pre-populated. Click **Propose** → action proposed → **Execute** in the Actions panel below → that recommendation drops out of the panel (already-executed filter).
8c. **Revert** the executed action → the recommendation reappears live (driven by the SSE-triggered incident refetch).
8d. As a `read_only` user the **Use this** buttons render disabled with the standard "Read-only role" tooltip.

**Response — new action kinds:**
9. Use **Propose action** → `quarantine_host_lab`. Set host to `lab-win10-01`. Execute → `LabAsset.notes` gets a quarantine marker; incident gets a note.
10. Use **Propose action** → `kill_process_lab`. Set host + pid + process_name. Execute → a `process_list` evidence request auto-appears in the Evidence Requests panel.
11. Use **Propose action** → `invalidate_lab_session`. Set user=alice, host=lab-win10-01. Execute → session row invalidated. **Revert** → session restored.
12. Use **Propose action** → `block_observable`. Kind=ip, value=10.0.0.99. Execute → `BlockedObservable` row created. Navigate to the entity for 10.0.0.99 → **BLOCKED** badge appears. Back on incident, **Revert** → badge disappears.
13. Use **Propose action** → `request_evidence`. Kind=process_list. Execute → new row in Evidence Requests panel.

**Standalone endpoint incident (medium severity):**
14. Click the `endpoint_compromise` incident → severity `medium`, confidence `0.60`. Rationale reads `"Endpoint signal ... without corroborating identity activity..."`.

**Detections dashboard:**
15. Navigate to `http://localhost:3000/detections`. Filter `rule_source=sigma` → only Sigma rows. Filter `rule_id=py.blocked_observable_match` → blocked-observable fire rows.

**Actions dashboard:**
16. Navigate to `http://localhost:3000/actions`. Filter `classification=disruptive` → quarantine + kill rows. Filter `classification=suggest_only` → evidence request rows.

**Lab:**
17. Navigate to `http://localhost:3000/lab`. Alice, lab-win10-01, 203.0.113.7 listed. Add/delete assets.

## Run individual smoke tests

```bash
# Phase 3 — basic detection and correlation (5 checks)
bash labs/smoke_test_phase3.sh

# Phase 5 — interactive response (10 checks, includes phase 3)
bash labs/smoke_test_phase5.sh

# Phase 6 — full chain including endpoint extension (15 checks)
bash labs/smoke_test_phase6.sh

# Phase 7 — Sigma + standalone endpoint + codegen (21 checks)
bash labs/smoke_test_phase7.sh

# Phase 8 — Wazuh bridge (27 checks; requires --profile wazuh + WAZUH_BRIDGE_ENABLED=true)
bash labs/smoke_test_phase8.sh

# Phase 9A — response handlers + blocked detection (14 checks)
bash labs/smoke_test_phase9a.sh

# Phase 15 — recommended response actions endpoint + lifecycle (21 checks)
bash labs/smoke_test_phase15.sh
```

### Phase 15 — recommended response actions

`bash labs/smoke_test_phase15.sh` reproduces the `credential_theft_chain` scenario inline via curl (no host-side python deps), then exercises the recommender against both incidents the scenario produces:

- **Chain incident (`identity_endpoint_chain`)** — verifies the endpoint returns 200 with at least 1 well-formed recommendation, all required fields populated, no excluded kinds (`tag_incident`/`elevate_severity`/`kill_process_lab`), sorted by priority ascending.
- **Parent incident (`identity_compromise`)** — verifies the top recommendation is `block_observable` on `203.0.113.42` (T1110 Brute Force boost). Then proposes + executes that action via `/v1/responses`, refetches recommendations, asserts the rec is filtered out (already-executed filter), reverts the action, and asserts the rec reappears.
- **Edge cases** — 404 for unknown incident id.

Honours `AUTH_REQUIRED=true` via `SMOKE_API_TOKEN` in `labs/.smoke-env` (mirrors `smoke_test_phase11.sh`). Auto-truncates DB + flushes Redis at the start; safe to re-run.

## Run unit tests

```bash
docker compose -f infra/compose/docker-compose.yml exec backend python -m pytest tests/unit/ -v
```

Note: the `tests/` directory is baked into the backend image (added in Phase 7). If the image predates Phase 7, rebuild first: `docker compose -f infra/compose/docker-compose.yml build backend`.

## TypeScript type check

```bash
docker exec compose-frontend-1 sh -c "cd /app && npx tsc --noEmit"
```

Should exit 0 with no output.

## Common operations

### Reset the DB (destroys all incident data)

```bash
cd infra/compose
docker compose down -v
docker compose up -d
```

The backend will auto-apply migrations on startup, including re-seeding lab_assets.

### Inspect Redis state

```bash
docker compose exec redis redis-cli
> KEYS *
> KEYS corr:*
```

### Tail backend logs

```bash
docker compose logs -f backend
```

### Open Postgres shell

```bash
docker compose exec postgres psql -U cybercat -d cybercat
```

Useful queries:
```sql
-- Check incident count and status
SELECT id, title, status, severity, kind FROM incidents ORDER BY opened_at DESC;

-- Check detections fired
SELECT rule_id, rule_source, severity_hint, created_at FROM detections ORDER BY created_at DESC;

-- Check auto-actions
SELECT kind, status, proposed_by, classification FROM actions ORDER BY proposed_at DESC;

-- Check evidence requests
SELECT id, incident_id, kind, status, requested_at FROM evidence_requests ORDER BY requested_at DESC;

-- Check blocked observables
SELECT id, kind, value, active, blocked_at FROM blocked_observables ORDER BY blocked_at DESC;

-- Check lab sessions
SELECT id, user_entity_id, host_entity_id, invalidated_at FROM lab_sessions ORDER BY opened_at DESC;
```

## Resource tips (Lenovo Legion Slim 5 Gen 8)

- Keep Wazuh off by default. Only start `--profile wazuh` when needed.
- Core stack (postgres + redis + backend + frontend) idles at ~3–4 GB RAM.
- If memory is tight: `docker compose stop frontend` and use the OpenAPI UI at `/docs` while developing backend-only changes.
- Stop lab VMs between demos.

## Troubleshooting

- **Backend won't start** — check `docker compose logs backend`. Most likely Postgres isn't ready yet; wait 10s and `docker compose restart backend`.
- **Frontend route returns 404** — new pages need a rebuild: `docker compose build frontend && docker compose up -d frontend`. Turbopack HMR doesn't pick up new route directories.
- **Smoke test fails on "incident count"** — the DB may have data from a previous run. The phase5/phase6 scripts truncate automatically; if running phase3 manually, do `docker compose down -v && docker compose up -d` first.
- **No incidents after smoke test** — check `docker compose logs backend` for Python errors. Confirm `detections_fired` and `incident_touched` are non-null in the curl output from the smoke test.
- **Port already in use** — run `docker compose down` first, or find and kill the conflicting process.
- **Wazuh indexer failing to start** — likely `vm.max_map_count` limit on WSL2. Run `sysctl -w vm.max_map_count=262144` inside the WSL distro.
- **`npm run gen:api:file` → ENOENT for `backend/openapi.json`** — the file lives inside the container, not on the host. Run `docker compose -f infra/compose/docker-compose.yml cp backend:/app/openapi.json backend/openapi.json` first, then retry `gen:api:file`.
- **`pytest tests/unit/` → "file or directory not found"** — the backend image was built before Phase 7 added `COPY tests/`. Rebuild: `docker compose -f infra/compose/docker-compose.yml build backend`.
- **Wazuh poller stuck / `events_ingested_total` stays 0** — check `docker compose logs backend | grep -i wazuh`. The most likely cause is a JSONB serialization error from a prior code version (`'list' object has no attribute 'encode'`): the poller died silently and `search_after` reset to NULL. Rebuild the backend image after updating `wazuh_poller.py`, then reset the cursor: `psql -U cybercat -d cybercat -c "UPDATE wazuh_cursor SET search_after=NULL, last_error=NULL WHERE id='singleton';"` and restart backend.

## Tailing the Live Event Stream

The SSE endpoint can be consumed directly with curl for ops debugging or verifying events are flowing:

```bash
# All topics
curl -N http://localhost:8000/v1/stream

# Single topic
curl -N "http://localhost:8000/v1/stream?topics=incidents"

# Multiple topics
curl -N "http://localhost:8000/v1/stream?topics=incidents,actions"
```

You will see heartbeat comments every 20s when nothing is happening:

```
: hb
```

And event lines when domain state changes:

```
id: 0195f3a2b4e800008a1f
event: incident.created
data: {"incident_id": "...", "kind": "identity_compromise", "severity": "high"}
```

See `docs/streaming.md` for the full event taxonomy.
