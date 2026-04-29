# Phase 16 — Custom Telemetry Agent (replaces Wazuh as default telemetry source)

> **Status: ✅ shipped 2026-04-28.** This file is the plan as it was approved; the implementation followed it with **one numbering deviation** — the ADR was filed as `ADR-0011-direct-agent-telemetry.md` because `ADR-0004` was already taken by the Wazuh bridge ADR. For the actual durable record see `docs/decisions/ADR-0011-direct-agent-telemetry.md`. For verification artifacts and measured outcomes see `PROJECT_STATE.md` § Phase 16. For operational mode guidance (observe-and-record vs observe-record-and-enforce) see `docs/runbook.md` § "Two operational modes."

## Context

CyberCat currently relies on Wazuh as its only telemetry source. The Wazuh stack (manager + indexer + agent) consumes ~1.8 GB of RAM at idle, dominating the memory footprint on the operator's 16 GB Windows laptop and pushing total system memory to 80%+ during dev sessions.

CLAUDE.md §6 already describes telemetry as pluggable: *"Telemetry intake (Wazuh + any direct agents/feeds)"* and *"the custom application layer is the star, Wazuh is upstream telemetry, not the product."* This phase makes that pluggability real by building a small Python agent that POSTs directly to the existing `/v1/events/raw` endpoint, then making it the default telemetry source while keeping the Wazuh integration intact and dormant.

**Outcome:** Default `./start.sh` brings up a ~700 MB stack (no Wazuh containers). The full identity-compromise scenario still ends-to-ends — same detections, same correlator, same incidents, same UI — but the events arrive from the custom agent. Wazuh stays available behind a `--profile wazuh` flag for "I want to demo the alternative" moments. No backend code changes; no test regressions.

## Confirmed architectural decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Stack match; reuse `labs/simulator/event_templates.py` builders verbatim; ships in days not weeks |
| v1 event scope | `auth.failed`, `auth.succeeded`, `session.started`, `session.ended` | Parseable from `/var/log/auth.log` alone; fires existing `auth_failed_burst` detector + `identity_compromise` correlator end-to-end |
| Future scope (note for later) | Add process + network events (auditd + conntrack) — Phase 16.9+ | Stronger demo, but ship narrow first |
| Deployment | Separate `cct-agent` container, mounts lab-debian's `/var/log/auth.log` read-only via shared volume | Clean boundary; matches one-purpose-per-container pattern |
| Wazuh handling | **Runtime replacement, not code deletion.** Containers stop running by default; backend code stays dormant; `WAZUH_BRIDGE_ENABLED=false` by default | Preserves all tests, all API surface, all UI behavior. Reversible via `--profile wazuh`. ADR-0004 records the decision. |

## Sub-phases (verify between each, mirroring Phase 1–15 cadence)

### Phase 16.1 — Foundations & ADR
- Write `docs/decisions/ADR-0004-direct-agent-telemetry.md`
- Create `agent/` directory at project root with skeleton: `pyproject.toml`, `Dockerfile`, `README.md`, empty package tree
- **Verify:** `python -m pip install -e ./agent` succeeds locally; `agent/` is gitignored only for `.venv` and `__pycache__`

### Phase 16.2 — sshd parser + event builders
- `agent/cct_agent/parsers/sshd.py` — parse the 4 sshd log line patterns we care about (failed password, accepted password, accepted publickey, session opened/closed)
- `agent/cct_agent/events.py` — event builder functions. **Derived from `labs/simulator/event_templates.py`** but with `"source": "direct"` instead of `"source": "seeder"`
- `agent/tests/test_sshd_parser.py` — fixtures of real auth.log lines (Debian + Ubuntu variants)
- **Verify:** `cd agent && pytest tests/test_sshd_parser.py` — all parser tests pass

### Phase 16.3 — File tail + checkpoint
- `agent/cct_agent/sources/tail.py` — async file tail, handles log rotation (inode change) and truncation
- `agent/cct_agent/checkpoint.py` — durable byte-offset state at `/var/lib/cct-agent/checkpoint.json`; load on startup, atomic write on each flush
- `agent/tests/test_tail.py`, `test_checkpoint.py` — covers: cold start, restart resumes from offset, log rotation
- **Verify:** `cd agent && pytest` — all tests pass

### Phase 16.4 — HTTP shipper + orchestration
- `agent/cct_agent/shipper.py` — `httpx.AsyncClient` POST loop with bounded queue (1000 events max, drop-oldest with metric on overflow), exponential backoff retry on 5xx/network errors, NEVER retry 4xx (means our payload is malformed, log + drop)
- `agent/cct_agent/config.py` — `AgentConfig` pydantic from env: `CCT_API_URL`, `CCT_AGENT_TOKEN`, `CCT_LOG_PATH`, `CCT_CHECKPOINT_PATH`, `CCT_BATCH_SIZE`, `CCT_FLUSH_INTERVAL_SECONDS`
- `agent/cct_agent/__main__.py` — top-level orchestration: load config → init checkpoint → spawn tail task → spawn shipper task → run forever, handle SIGTERM gracefully
- `agent/tests/test_shipper.py` — uses `respx` to mock the backend; covers: 201 happy path, 4xx no-retry, 5xx retry, network error retry, queue overflow
- **Verify:** `cd agent && pytest` — all tests pass; manual smoke: `python -m cct_agent` against a real local backend with hand-crafted auth.log

### Phase 16.5 — Compose integration + token bootstrap
- `infra/compose/docker-compose.yml` — add `cct-agent` service:
  - `build: ../../agent`
  - `profiles: [agent]` (initially behind explicit profile, will become default in 16.6)
  - depends_on: backend (healthy)
  - mounts shared volume with lab-debian's `/var/log/auth.log` (read-only)
  - reads `CCT_AGENT_TOKEN` from compose env
- `infra/compose/.env.example` — add `CCT_AGENT_TOKEN=` placeholder with comment explaining it's auto-provisioned
- `start.sh` — on first run, if `CCT_AGENT_TOKEN` empty in `.env`, run `docker compose exec backend python -m app.cli issue-token --email cct-agent@local --name cct-agent` and write the resulting token into `.env`
- **Verify:** `./start.sh` (with manual `--profile agent`) brings the agent up; `docker logs compose-cct-agent-1` shows successful event POSTs

### Phase 16.6 — Make agent the default; demote Wazuh to opt-in
- Update `start.sh` default `--profile` set to `core agent` (Wazuh now requires explicit `--profile wazuh`)
- `infra/compose/.env.example` — set `WAZUH_BRIDGE_ENABLED=false` as the default
- `start.sh` startup banner — print "Wazuh disabled by default. Run with `--profile wazuh` to enable."
- **Verify:**
  - Full pytest suite still passes (target: 173/173 — no test regressions)
  - `./start.sh` brings up 6 containers (postgres/redis/backend/frontend/lab-debian/cct-agent), no Wazuh containers
  - Frontend at `http://localhost:3000/incidents` loads cleanly
  - `GET /v1/wazuh/status` returns `{"enabled": false, "reachable": false, ...}` without erroring

### Phase 16.7 — End-to-end smoke test
- `labs/smoke_test_agent.sh`:
  1. Bring up `core` + `agent` profiles
  2. Wait for agent to log `agent ready, tailing /var/log/auth.log`
  3. Inside lab-debian, trigger 5 fake ssh failures: `for i in {1..5}; do ssh -o ConnectTimeout=2 baduser@localhost true 2>/dev/null; done`
  4. Wait 10s for ingestion
  5. Assert: `GET /v1/events?source=direct&kind=auth.failed` returns ≥ 5 items
  6. Assert: `GET /v1/detections` shows a fresh `py.auth.failed_burst` detection
  7. Assert: `GET /v1/incidents?kind=identity_compromise` shows a fresh incident
- **Verify:** `bash labs/smoke_test_agent.sh` returns exit 0; full pytest still 173/173

### Phase 16.8 — Documentation + memory note
- `docs/architecture.md` — add "Telemetry sources" section showing pluggable design with agent as default and Wazuh as alternative
- `docs/runbook.md` — agent profile flags, token rotation procedure, troubleshooting
- `Project Brief.md` — update positioning: "CyberCat ships with a custom telemetry agent and supports Wazuh as an optional backend"
- `PROJECT_STATE.md` — mark Phase 16 complete with verification artifact paths
- New memory file `project_phase16.md` summarizing what shipped + verification status
- **Verify:** docs render cleanly; PROJECT_STATE.md and memory note reflect reality

## Files created (new)

```
docs/decisions/ADR-0004-direct-agent-telemetry.md
agent/pyproject.toml
agent/Dockerfile
agent/README.md
agent/cct_agent/__init__.py
agent/cct_agent/__main__.py
agent/cct_agent/config.py
agent/cct_agent/checkpoint.py
agent/cct_agent/shipper.py
agent/cct_agent/events.py
agent/cct_agent/parsers/__init__.py
agent/cct_agent/parsers/sshd.py
agent/cct_agent/sources/__init__.py
agent/cct_agent/sources/tail.py
agent/tests/__init__.py
agent/tests/test_sshd_parser.py
agent/tests/test_tail.py
agent/tests/test_checkpoint.py
agent/tests/test_shipper.py
agent/tests/fixtures/auth_debian.log
agent/tests/fixtures/auth_ubuntu.log
labs/smoke_test_agent.sh
```

## Files modified (minimal touches)

| File | Change |
|---|---|
| `infra/compose/docker-compose.yml` | Add `cct-agent` service with profile + shared log volume |
| `infra/compose/.env.example` | Add `CCT_AGENT_TOKEN=`, set `WAZUH_BRIDGE_ENABLED=false` |
| `start.sh` | Default profile → `core agent`; bootstrap agent token on first run; print Wazuh-disabled banner |
| `docs/architecture.md` | Add "Telemetry sources" section |
| `docs/runbook.md` | Add agent operation section |
| `Project Brief.md` | Update positioning |
| `PROJECT_STATE.md` | Mark Phase 16 status |

## Files explicitly NOT touched (this is the "don't break what we built" promise)

| File | Why it's safe to leave alone |
|---|---|
| `backend/app/api/routers/events.py` | `/v1/events/raw` already accepts `source="direct"` |
| `backend/app/api/schemas/events.py` | `RawEventIn.source` literal already includes `"direct"` |
| `backend/app/enums.py` | `EventSource.direct` already exists |
| `backend/app/ingest/normalizer.py` | `KNOWN_KINDS` already includes all v1 kinds with correct required fields |
| `backend/app/ingest/wazuh_poller.py`, `wazuh_decoder.py` | Dormant when `WAZUH_BRIDGE_ENABLED=false`; existing tests still pass against this code |
| `backend/app/api/routers/wazuh.py` | `/v1/wazuh/status` correctly returns `enabled=false` when bridge disabled |
| `backend/app/response/dispatchers/wazuh_ar.py` | Active Response is opt-in via `WAZUH_AR_ENABLED`; out of v1 scope |
| `backend/alembic/versions/0004_add_wazuh_cursor.py` | Migration stays applied; `wazuh_cursor` row remains; no churn |
| All detection rules under `backend/app/detection/rules/` | Already key on `normalized` fields, work identically on agent-sourced events |
| All Sigma rules under `backend/app/detection/sigma_pack/` | Same — match on canonical normalized fields |
| Frontend (`frontend/`) | No API contract change; existing Wazuh status panel renders "disabled" gracefully |
| `backend/tests/` | Existing 173 tests must continue passing; agent code lives in separate `agent/tests/` |

## Existing code to REUSE (do not reinvent)

| Existing artifact | What we reuse it for |
|---|---|
| `labs/simulator/event_templates.py` (`auth_failed`, `auth_succeeded`, `session_started`) | Copy-derive into `agent/cct_agent/events.py`, change `"source": "seeder"` → `"source": "direct"` |
| `labs/simulator/client.py` (`SimulatorClient.post_event` httpx async pattern) | Model the shipper after this; same `httpx.AsyncClient`, same `Authorization: Bearer` header pattern |
| `backend/app/cli.py:issue-token` | Called by `start.sh` first-run hook to mint the agent's token |
| `backend/app/ingest/normalizer.py:_REQUIRED` | Reference for what fields each event kind must populate (single source of truth — agent must satisfy this) |
| `backend/tests/integration/test_identity_endpoint_chain.py` | Pattern to follow for the agent's smoke test |

## End-to-end verification (after Phase 16.7)

```bash
# 1. Clean slate
./stop.sh
docker compose -f infra/compose/docker-compose.yml down -v

# 2. Bring up new default (no Wazuh)
./start.sh

# 3. Confirm Wazuh containers are NOT running
docker ps --format "{{.Names}}"
# expect: compose-postgres-1, compose-redis-1, compose-backend-1,
#         compose-frontend-1, compose-lab-debian-1, compose-cct-agent-1
#         (NO wazuh-manager, NO wazuh-indexer)

# 4. Confirm agent is shipping events
docker logs compose-cct-agent-1 --tail 30
# expect: "agent ready, tailing /var/log/auth.log"
#         followed by "shipped N events" lines

# 5. Run smoke test
bash labs/smoke_test_agent.sh
# expect: 7/7 assertions pass, exit 0

# 6. Run backend pytest (no Wazuh-related failures should appear)
"C:/Users/oziel/AppData/Local/Programs/Python/Python313/python.exe" -m pytest backend/tests
# expect: 173 passed, 0 failed (Wazuh tests still pass — they test code not containers)

# 7. Run agent pytest
cd agent && pytest
# expect: all green

# 8. Memory check
docker stats --no-stream
# expect total RSS across compose containers ~700-900 MB (vs ~3 GB with Wazuh)

# 9. UI smoke
curl -sf http://localhost:3000/incidents -o /dev/null -w "%{http_code}\n"
# expect: 200
```

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| auth.log parser misses a Linux distro variant | Test fixtures cover both Debian and Ubuntu sshd line formats. Unparseable lines are logged as warnings, never crash the agent. |
| Backend down → events queue grows unbounded | Bounded in-memory queue (1000 events). Overflow drops oldest with a metric. No disk spool in v1 — keep it simple. |
| Token rotation | Out of scope for v1. Agent reads token from env at startup; restart to rotate. Documented in runbook. |
| Default behavior change of `start.sh` confuses future-you | ADR-0004 records the decision. `start.sh` prints "Wazuh disabled by default; pass --profile wazuh to enable" on startup. Runbook documents both modes. |
| lab-debian's installed Wazuh agent is now orphaned | Acceptable in v1 — it just runs and emits to a Wazuh manager that isn't there. Phase 16.9 can either remove it from the lab-debian image or repurpose it. Document in ADR. |
| Containers can't see each other's `/var/log` | Use a named Docker volume mounted into both lab-debian (read/write) and cct-agent (read-only). Verified by Phase 16.7 smoke. |

## Deferred to later phases (explicitly OUT of Phase 16)

- **Phase 16.9** — Process events via auditd integration (`process.created`, `process.exited`). Adds parser, completes the endpoint-compromise demo without Wazuh.
- **Phase 16.10** — Network events via conntrack (`network.connection`).
- **Phase 17 (optional)** — Go rewrite of the hot path; native binary build.
- **Phase 18 (optional)** — Token rotation + multi-source dedupe.
- **Wazuh code deletion** — Not on the roadmap. Wazuh integration stays as a working alternative backend indefinitely. Revisit only if/when it becomes a maintenance burden.
