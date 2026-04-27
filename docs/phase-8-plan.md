# Phase 8 Execution Plan — Wazuh Bridge (Pull-Mode Indexer Poller)

Drafted 2026-04-21 during a planning-only session. Implementation will be handed off to a separate model. Picks up after Phase 7 once smoke checks 17–21 are green.

Read this first, then `PROJECT_STATE.md`, then `docs/decisions/ADR-0003-resource-constraints.md`, then `docs/architecture.md` §3.1 (ingest adapters), then `backend/app/api/routers/events.py:24-86` — the exact pipeline the poller must reuse rather than duplicate.

---

## Context

Phase 5 made response honest. Phase 6 made the chain visible. Phase 7 made detection credible (Sigma + standalone endpoint + codegen). **Phase 8 is the first time a CyberCat incident is born from a real log that passed through a real detection engine operated by someone else.** Until now every event has been synthetic, authored by `EventSource.seeder` or `EventSource.direct`. A threat-informed IR platform without a real sensor integration is a simulator.

Phase 8 is also the first stress-test of two ADR-gated principles that have never faced third-party telemetry:

- **ADR-0002: asyncio-only** — no queue, no worker, no external scheduler.
- **ADR-0003: restartable by design** — Wazuh offline during dev must not block development; backend restart must not drop ingested alerts.

If both hold here, they hold for anything.

**Scope decisions locked before planning (do not revisit during implementation):**

1. **Pull from the Wazuh Indexer** via OpenSearch `_search` with cursored `search_after`. Not push. Not Filebeat-to-us. Not Syslog. Not Integrator webhook. Rationale in ADR-0004 (§3k).
2. **Response side-effects (Active Response wiring) deferred to Phase 9.** The five handlers in `backend/app/response/handlers/stubs.py` keep returning `skipped`. Phase 8 is ingest-only. Bundling egress would double the verification gate.
3. **Lab endpoint: a `lab-debian` container** (Debian 12 slim + sshd + auditd + Wazuh agent) shipped as a third service under `--profile wazuh`. No VirtualBox, no hypervisor, no manual agent install — ~150 MB RAM, ~2 s boot, `docker compose exec` automates every demo step. Wazuh's OOB decoders handle sshd/auditd unchanged. Windows (Sysmon) lab deferred to Phase 9+.

**Prerequisite:** Phase 7 complete. Smoke test 17–21 green, `openapi.json` extracted and committed, `npm run typecheck` clean. PROJECT_STATE reports these are pending a re-run; the implementing session must confirm green before opening Phase 8.

---

## 0. Why this phase matters

Every "threat-informed SOAR" deck says the words "Sigma" (handled in Phase 7) and "real telemetry bridge" (this phase). Without a live Wazuh loop, the project reads as a custom rule engine against a seeder. With it, the custom application layer — normalization, correlation, incident model, response policy, analyst UX — has a legitimate upstream and the exact same product logic demonstrably reacts to a real sensor.

### Design principles driving the differentiation

1. **Pull, not push.** Asyncio poller inside the FastAPI process queries the Wazuh Indexer REST API on an interval. No inbound webhook, no Integrator plug-in, no Filebeat-to-CyberCat output, no Syslog receiver. One attack surface less and the bridge is restart-safe by construction.
2. **Zero schema change.** `EventSource.wazuh` is already in the enum (`backend/app/enums.py:15`) and migration 0001. The bridge is one new small table for cursor state and nothing else.
3. **Reuse the ingest pipeline verbatim.** The poller calls the same `extract_and_link_entities → run_detectors → run_correlators → propose_and_execute_auto_actions` sequence `events.py` uses today (currently inlined at `backend/app/api/routers/events.py:49-79`). Phase 8 extracts it into `backend/app/ingest/pipeline.py` so both callers share one code path. No drift. No second correlation path.
4. **Wazuh-down is not a product outage.** Bridge off by default in dev. When on and unreachable, the rest of the platform (direct ingest, seeder, frontend, correlation on synthetic input) stays fully functional. The Phase 7 smoke test must remain green with Wazuh both off and up.

---

## 1. Pre-work

### 1a. Schema audit

- `EventSource.wazuh` exists (`backend/app/enums.py:15`, migration `0001_initial_schema.py:41`). Zero change.
- `Event.(source, dedupe_key)` unique constraint namespaces Wazuh alerts cleanly away from the seeder — `alert._id` is the dedupe anchor, `source=wazuh` prevents any cross-source collision.
- One new migration: `0004_add_wazuh_cursor.py` — single-row state table. See §3c.

### 1b. Config surface (extend `backend/app/config.py`)

All nine fields have safe defaults. `WAZUH_BRIDGE_ENABLED=false` short-circuits the lifespan hook — the poller never starts unless explicitly enabled.

| Env var | Default | Purpose |
|---|---|---|
| `WAZUH_BRIDGE_ENABLED` | `false` | Master switch. Off in dev; on under `--profile wazuh`. |
| `WAZUH_INDEXER_URL` | `https://wazuh-indexer:9200` | OpenSearch base URL (internal compose DNS). |
| `WAZUH_INDEXER_USER` | `admin` | Built-in admin. v1 only; Phase 9 provisions `cybercat_reader`. |
| `WAZUH_INDEXER_PASSWORD` | *(required if enabled)* | Set in `.env`, not in compose defaults. |
| `WAZUH_INDEXER_INDEX_PATTERN` | `wazuh-alerts-*` | OOB daily indices. |
| `WAZUH_POLL_INTERVAL_SECONDS` | `5` | Cadence vs. lag tradeoff. See §7. |
| `WAZUH_POLL_BATCH_SIZE` | `100` | Max alerts per tick. Loop drains without sleeping when a tick returns a full batch (§3e). |
| `WAZUH_INDEXER_VERIFY_TLS` | `false` | v1 accepts self-signed. Security debt documented in ADR-0004. |
| `WAZUH_FIRST_RUN_LOOKBACK_MINUTES` | `5` | Cold-start bound — avoids importing months of history. |

### 1c. Compose additions (profile-gated)

Replace the placeholder comment at `infra/compose/docker-compose.yml:65-69` with real services under `profiles: [wazuh]`:

- `wazuh-indexer` (image `wazuh/wazuh-indexer:4.9.2`): `discovery.type=single-node`, `OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g` (critical — default is 1–2 GB auto). Healthcheck `curl -sk -u admin:$WAZUH_INDEXER_PASSWORD https://localhost:9200/_cluster/health` expects 200.
- `wazuh-manager` (image `wazuh/wazuh-manager:4.9.2`): OOB Filebeat ships to the indexer. Expose 1514/udp (agent events) and 1515/tcp (enrollment). `depends_on: wazuh-indexer: condition: service_healthy`.
- `lab-debian` (built locally from `infra/lab-debian/Dockerfile`, `FROM debian:12-slim`): installs `openssh-server`, `auditd`, and the Wazuh agent 4.9.2. Entrypoint starts sshd + auditd + agent. Auto-enrolls against `wazuh-manager` using env var `WAZUH_MANAGER=wazuh-manager` + `WAZUH_REGISTRATION_PASSWORD` (mounted from manager at boot, or baked via build-arg for lab). Privileged (or `CAP_AUDIT_WRITE` + `CAP_AUDIT_CONTROL`) so auditd can emit EXECVE. Two lab users baked in at build time: `realuser` (valid password) and `baduser` (no matching password, used for brute-force attempts). `depends_on: wazuh-manager: condition: service_healthy`. Healthcheck = `pgrep sshd && pgrep wazuh-agentd`.
- **Skip `wazuh-dashboard` deliberately.** It's a ~700 MB Kibana fork that duplicates CyberCat's UI with nothing CyberCat lacks. Calling this out explicitly in ADR-0004 and the runbook; it's a real architectural decision, not an oversight.

Volumes: `wazuh_indexer_data`, `wazuh_manager_config`, `wazuh_manager_logs`. Certs: accept the installer-generated self-signed bundle baked into the image. Do **not** attempt to pre-provision a CA in Phase 8.

---

## 2. Decisions locked

| Decision | Choice | Reason |
|---|---|---|
| Bridge mechanism | Pull from Wazuh Indexer via `_search` with `sort:[@timestamp asc, _id asc]` | Restart-safe cursor; no inbound webhook; matches ADR-0002 asyncio-only principle. |
| Host process | FastAPI lifespan — poller task registered beside `init_redis` at `backend/app/main.py:26-29` | One process; one operator model; no second container. |
| Wazuh services | manager + indexer + `lab-debian` container; **no dashboard** | Saves ~700 MB RAM; dashboard adds no CyberCat value. `lab-debian` replaces the original VM plan — lighter on the Legion, Claude Code automates it, zero hypervisor install. |
| Images | `wazuh/wazuh-manager:4.9.2`, `wazuh/wazuh-indexer:4.9.2` | Pin current stable; matches Wazuh's published OOB deploy docs. |
| Indexer heap | `-Xms1g -Xmx1g` | Non-negotiable to fit Tier A+B ≤10 GB (ADR-0003). |
| TLS verification | `httpx.AsyncClient(verify=False)` in v1 | Wazuh self-signed certs are notorious. Debt + TODO documented in ADR-0004. |
| Cursor shape | `search_after = [iso_timestamp_str, doc_id_str]` stored as JSONB array | Tuple cursor is clock-skew-safe. `_id` alone doesn't paginate, `timestamp` alone isn't unique. |
| Cold-start query | First call uses a `range` filter on `@timestamp >= now - lookback_minutes` with `size=batch, sort:[...]`. `search_after` only populates from tick 2 onward. | Simpler + semantically correct. An empty-string `_id` tiebreaker is a footgun. |
| First-run lookback | `now() - WAZUH_FIRST_RUN_LOOKBACK_MINUTES` | Bound on historical import; operator can extend when they want backfill. |
| Rule whitelist (query-time) | `rule.groups` ∈ `{authentication_success, authentication_failed, audit}` | Wazuh OOB fires hundreds of rules we can't normalize; filter server-side to save bandwidth and decoder drops. |
| Dedup key | `alert._id` (indexer doc id) | Stable, unique, Wazuh-guaranteed. Collides with nothing because `source=wazuh`. |
| Decoder failure | Log WARN, increment `events_dropped_total`, **advance cursor past the bad doc** | Never halt the cursor on one malformed alert. |
| DB session in poller | Short-lived session per tick via `async_session_maker` — never hold across `asyncio.sleep` | Long-held sessions wedge the pool during outages. |
| Status endpoint auth | Unauthenticated (matches `/healthz`) | Single-operator v1 posture (ADR-0001). |
| Pollstop on shutdown | Lifespan sets `stop_event`, `await asyncio.wait_for(task, timeout=10)` | Clean shutdown; no zombie tasks. |

---

## 3. Work plan (ordered — do not skip ahead)

### 3a. Extract shared ingest pipeline (backend, do first — clears the poller's path)

The logic at `backend/app/api/routers/events.py:49-79` (dedup → Event insert → entity extract → detectors → correlators → commit → auto-actions) is the critical path the poller must reuse.

- **New:** `backend/app/ingest/pipeline.py` exposing:
  ```
  async def ingest_normalized_event(
      db: AsyncSession,
      redis: Redis,
      *,
      source: EventSource,
      kind: str,
      occurred_at: datetime,
      raw: dict,
      normalized: dict,
      dedupe_key: str | None,
  ) -> IngestResult
  ```
  `IngestResult` is a small dataclass: `event_id: UUID | None`, `dedup_hit: bool`, `detections_fired: int`, `incident_touched: UUID | None`.
- **Modify:** `backend/app/api/routers/events.py` — replace lines 49–79 with a single helper call. Response shape unchanged.
- **Regression:** existing smoke tests (1–21) must remain green after this refactor before any Wazuh code is added.

### 3b. Cursor table + model + migration

- **New migration:** `backend/alembic/versions/0004_add_wazuh_cursor.py` creating `wazuh_cursor`:
  - `id: text PRIMARY KEY` — literal `'singleton'`
  - `search_after: jsonb NULL` — array `[iso_ts, doc_id]`
  - `last_poll_at: timestamptz NULL`
  - `last_success_at: timestamptz NULL`
  - `last_error: text NULL`
  - `events_ingested_total: bigint NOT NULL DEFAULT 0`
  - `events_dropped_total: bigint NOT NULL DEFAULT 0`
- **New model:** `WazuhCursor` in `backend/app/db/models.py`.
- **First-row insert:** lazy — the poller `INSERT ... ON CONFLICT DO NOTHING` on the singleton row at startup. Cursor stays `NULL` until the first successful tick.

### 3c. Wazuh decoder (`backend/app/ingest/wazuh_decoder.py`)

`def decode_wazuh_alert(alert: dict) -> DecodedEvent | None`. Returns `None` for drops.

**Mapping table — exhaustive for Phase 8:**

| Wazuh signal | → `kind` | `normalized` mapping |
|---|---|---|
| `rule.groups` ⊇ `{authentication_failed, sshd}` or `{syslog, sshd, authentication_failed}` | `auth.failed` | `user ← data.srcuser \|\| data.dstuser`, `source_ip ← data.srcip`, `auth_type ← "ssh"` |
| `rule.groups` ⊇ `{authentication_success, sshd}` | `auth.succeeded` | `user ← data.dstuser`, `source_ip ← data.srcip`, `auth_type ← "ssh"` |
| `rule.groups` ⊇ `{audit}` with `data.audit.type == "EXECVE"` (or `rule.groups` includes `audit_command`) | `process.created` | `host ← agent.name`, `pid ← int(data.audit.pid)`, `ppid ← int(data.audit.ppid)`, `image ← data.audit.exe`, `cmdline ← data.audit.command` (if present) **else** join `data.audit.a0 data.audit.a1 ...` args with spaces, `user ← data.audit.auid` (resolved) |

Common for every kind:
- `occurred_at ← parse(alert.timestamp)` (UTC)
- `raw ← alert` (full dict preserved — explainability requirement)
- `dedupe_key ← alert._id` (from the surrounding OpenSearch hit envelope, not `alert.id`)
- `source = EventSource.wazuh`

**Drop policy** (return `None`, increment `events_dropped_total`, log `event.source=wazuh event.dropped rule.id=<n> reason=<str>` at WARN):
- `rule.groups` doesn't intersect the whitelist.
- `agent.name` missing when kind would be `process.created`.
- `data.srcip` missing when kind would be `auth.*` (correlators need it for the identity_compromise brute-force window).
- `alert.timestamp` unparseable.

### 3d. Poller (`backend/app/ingest/wazuh_poller.py`)

`async def poller_loop(stop_event: asyncio.Event) -> None` plus `def build_query(cursor_value: list | None, batch: int, first_run_lookback_min: int) -> dict`.

**Query shape:**
```
POST {indexer_url}/{index_pattern}/_search
{
  "size": <batch>,
  "sort": [{"@timestamp": "asc"}, {"_id": "asc"}],
  "query": {"bool": {"filter": [
    {"terms": {"rule.groups": ["authentication_failed","authentication_success","audit"]}},
    <if cursor is None: {"range": {"@timestamp": {"gte": "now-<N>m"}}}>
  ]}},
  <if cursor is not None: "search_after": <cursor>>
}
```

**Loop outline:**
1. Open a single `httpx.AsyncClient(verify=settings.wazuh_indexer_verify_tls, auth=(user, pass), timeout=10)`. Reuse across ticks.
2. On startup: `INSERT INTO wazuh_cursor (id) VALUES ('singleton') ON CONFLICT DO NOTHING`.
3. Each tick (short-lived session per tick):
   a. `SELECT * FROM wazuh_cursor WHERE id='singleton'`.
   b. POST query. On `httpx.HTTPError` or non-2xx → update `last_error, last_poll_at=now`; sleep with backoff (local variable, exponential, capped 60s); continue.
   c. For each hit: call `decode_wazuh_alert(hit._source | {"_id": hit._id})`; if `None`, increment dropped-count and skip; else call `ingest_normalized_event(...)` from §3a.
   d. After batch: cursor `search_after = last_hit.sort`; update `last_success_at=now, last_error=NULL, events_ingested_total += accepted, events_dropped_total += dropped`; commit.
   e. If `len(hits) < batch_size`, sleep `WAZUH_POLL_INTERVAL_SECONDS`; else loop immediately (drain mode).
4. `stop_event.is_set()` checked at the top of each iteration for clean shutdown.

**Resilience:** 10 consecutive identical errors → the `last_error` stabilizes at the message and poller keeps trying at 60s intervals. It never exits. Lifespan shutdown is the only termination path.

### 3e. Lifespan wiring (`backend/app/main.py`)

Register the poller task beside `init_redis`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_redis()
    stop_event = asyncio.Event()
    poller_task = None
    if settings.wazuh_bridge_enabled:
        poller_task = asyncio.create_task(poller_loop(stop_event))
    yield
    stop_event.set()
    if poller_task is not None:
        try:
            await asyncio.wait_for(poller_task, timeout=10)
        except asyncio.TimeoutError:
            poller_task.cancel()
    await close_redis()
```

`WAZUH_BRIDGE_ENABLED` is the only gate — the import of the poller module is fine to keep unconditional (it's a few hundred lines with no heavy deps).

### 3f. Status endpoint + router (`backend/app/api/routers/wazuh.py`)

`GET /v1/wazuh/status` returns:
```
{
  enabled: bool,
  reachable: bool,
  last_poll_at: iso | null,
  last_success_at: iso | null,
  lag_seconds: int | null,
  events_ingested_total: int,
  events_dropped_total: int,
  last_error: string | null
}
```
`reachable = (last_error is None) AND (last_success_at is within 3× poll_interval)`. `lag_seconds = now - last_success_at` when defined.

Register in `backend/app/main.py` alongside the other routers (around lines 49–55). Declare the `ErrorEnvelope` responses pattern Phase 7 established. Unauthenticated — same posture as `/healthz`.

**Regenerate OpenAPI + TS types** per Phase 7 workflow after this endpoint lands:
```
docker compose exec backend python -m scripts.dump_openapi
docker compose cp backend:/app/openapi.json backend/openapi.json
cd frontend && npm run gen:api:file && npm run typecheck
```

### 3g. Frontend badge (`frontend/app/components/WazuhBridgeBadge.tsx`)

Small component — no new page, no new route, no new fetcher boilerplate (uses the generated `api.ts` client). Polls `/v1/wazuh/status` every 10 s via the existing `usePolling` hook.

States:
- `!enabled` → gray `StatusPill` "Bridge off"
- `enabled && reachable` → green "Wazuh • live" (when `lag_seconds < 30`) or "Wazuh • <RelativeTime>"
- `enabled && !reachable` → amber "Wazuh unreachable"; `title={last_error}` tooltip

Insert in `frontend/app/layout.tsx` top-nav area next to the existing nav links.

### 3h. Lab endpoint: `lab-debian` container + scenario doc

**Image build (`infra/lab-debian/Dockerfile`):**
- `FROM debian:12-slim`.
- `apt install -y openssh-server auditd curl gnupg lsb-release procps`.
- Install Wazuh agent 4.9.2 from the official repo (`curl -sO https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/wazuh-agent_4.9.2-1_amd64.deb`).
- Seed two users at build time: `realuser` with a known password (build-arg) and `baduser` with a random unguessable one (so `sshpass -p wrong ssh baduser@...` always fails).
- Seed auditd rule for execve: `-a always,exit -F arch=b64 -S execve -k cybercat_exec`.
- Copy `infra/lab-debian/entrypoint.sh`.

**Entrypoint (`infra/lab-debian/entrypoint.sh`):**
1. Generate ssh host keys if missing.
2. `service auditd start`.
3. Read `WAZUH_REGISTRATION_PASSWORD` (injected at runtime via compose env or shared volume with manager).
4. Register with manager: `/var/ossec/bin/agent-auth -m wazuh-manager -P "$WAZUH_REGISTRATION_PASSWORD"`.
5. `service wazuh-agent start`.
6. `exec /usr/sbin/sshd -D` (foreground, PID 1).

**Scenario doc (`docs/scenarios/wazuh-ssh-brute-force.md`):**

End-to-end recipe, all from the host shell — Claude Code can run each step directly:

```bash
# 1. Bring up the wazuh profile (includes lab-debian).
cd infra/compose
docker compose --profile wazuh up -d

# 2. Confirm the agent enrolled with the manager.
docker compose exec wazuh-manager /var/ossec/bin/agent_control -l
# → expect: lab-debian listed as Active.

# 3. Confirm CyberCat bridge is live.
curl -s http://localhost:8000/v1/wazuh/status | jq .reachable
# → true

# 4. Fire the brute-force chain FROM INSIDE the lab-debian container
#    (so sshd sees the connection and Wazuh sees the log).
docker compose exec lab-debian bash -c '
  for i in 1 2 3 4; do
    sshpass -p wrong ssh -o StrictHostKeyChecking=no baduser@localhost true 2>/dev/null || true
  done
  sshpass -p lab123 ssh -o StrictHostKeyChecking=no realuser@localhost true
'
# → Four authentication_failed + one authentication_success emitted within seconds.

# 5. Watch the incident appear.
sleep 10
curl -s 'http://localhost:8000/v1/incidents?kind=identity_compromise' | jq '.items[0] | {id,title,severity,status}'
# → One incident. Open the UI at http://localhost:3000/incidents to drill in.
```

Expected in the UI within ~10 s of step 4:
- `identity_compromise` incident at severity `high`.
- Events tagged `source=wazuh` visible in the timeline.
- Raw Wazuh alert JSON (including `rule.id`, `rule.groups`, `agent.name=lab-debian`) visible when the event row is expanded.
- `T1110` (Brute Force) ATT&CK tag rendered if present in the Phase 6 catalog.

**Why a container, not a VM:**
- 150 MB RAM vs. ~1.5 GB for a VirtualBox Debian guest.
- 2 s cold start vs. 45 s VM boot.
- Zero hypervisor dependency — the demo reproduces on any machine with Docker.
- Claude Code automates every step via `docker compose exec`; no VM-side manual work.
- Wazuh officially supports agents-in-containers; this is a documented production pattern, not a shortcut.

### 3i. Runbook update (`docs/runbook.md:99-105`)

Replace the `(TBI — Phase 8)` block with:
- `--profile wazuh up -d` recipe.
- Note that the Wazuh dashboard is deliberately not started (pointer to ADR-0004 §consequences).
- Env vars to set in `.env` (`WAZUH_BRIDGE_ENABLED=true`, `WAZUH_INDEXER_PASSWORD=<...>`).
- Pointer to `docs/scenarios/wazuh-ssh-brute-force.md`.
- Troubleshooting: `vm.max_map_count` for WSL2 (already present at line 308 — reinforce the link).
- Fresh-install note: manager auto-generates the registration password on first boot; operator reads it with `docker compose exec wazuh-manager cat /var/ossec/etc/authd.pass` for agent enrollment.

### 3j. ADR-0004 (`docs/decisions/ADR-0004-wazuh-bridge.md`)

- **Context:** need real telemetry; mechanisms Wazuh offers (Integrator, Filebeat output, Syslog forwarder, Indexer REST, archives tail).
- **Decision:** pull from indexer via asyncio poller inside backend process.
- **Rationale:** restart-safe cursor in Postgres; matches ADR-0002 no-queue principle; Wazuh-down doesn't block dev; no inbound port exposure; operator model stays one-process.
- **Alternatives considered:**
  - *Integrator → webhook:* needs backend accepting inbound HTTPS with its own auth/TLS; tied to manager lifecycle; lost alerts when backend is down.
  - *Filebeat → /v1/events/raw:* bypasses Wazuh's rule engine entirely — defeats the integration story.
  - *Syslog forwarder:* re-parsing text Wazuh already structured.
  - *Archives folder tail:* brittle file-format coupling, not API-contractual.
- **Consequences:** polling lag bounded by interval; first-run must lookback-limit; `_id` is the dedupe anchor.
- **Security notes (debt, tracked):** TLS verification off in v1 (self-signed); `admin` indexer user in v1; Phase 9 provisions a `cybercat_reader` role and pins the CA.

### 3k. Tests

- **Unit (`backend/tests/unit/test_wazuh_decoder.py`)** — three JSON fixtures under `backend/tests/fixtures/wazuh/` (sshd-failed, sshd-success, auditd-execve). Assert the normalized output per mapping table. Negative cases: missing `data.srcip` → drop; unknown `rule.groups` → drop; unparseable timestamp → drop. No Wazuh needed.
- **Integration (`backend/tests/integration/test_wazuh_poller.py`)** — `httpx_mock` stubs the indexer. Covers:
  (i) first-run uses range query, no `search_after`;
  (ii) cursor advances to last hit's `sort` tuple;
  (iii) re-poll with same docs returns `dedup_hit=True` via unique constraint;
  (iv) unreachable → `last_error` set, cursor unchanged;
  (v) reachable-again resumes from stored cursor;
  (vi) malformed alert dropped, cursor still advances;
  (vii) decoder `None` result doesn't wedge the loop.
- **Smoke (`labs/smoke_test_phase8.sh`)** — requires `docker compose --profile wazuh up -d` and `WAZUH_BRIDGE_ENABLED=true`. Sources `smoke_test_phase7.sh` first (regress 21 checks). New checks 22–27:
  22. Manager health 200; `agent_control -l` shows `lab-debian` as Active.
  23. Indexer `_cluster/health` returns `green` or `yellow`.
  24. `/v1/wazuh/status.enabled == true`.
  25. From inside `lab-debian`: four `sshpass -p wrong ssh baduser@localhost` attempts. Within 15 s, `/v1/wazuh/status.events_ingested_total` has advanced and `GET /v1/events?source=wazuh` returns ≥ 4 events with `kind=auth.failed`.
  26. From inside `lab-debian`: one successful `sshpass -p lab123 ssh realuser@localhost`. Within 10 s, the pipeline produces ≥ 1 `auth.succeeded` event and `identity_compromise` correlator fires.
  27. `GET /v1/incidents?kind=identity_compromise` returns one incident whose linked events include `source=wazuh`; incident severity is `high`.

  **Fallback for CI or when the agent isn't ready yet:** direct-POST a fixture alert doc into `wazuh-alerts-YYYY.MM.DD` via `curl -ku admin:$PASS https://wazuh-indexer:9200/.../_doc` to exercise the pull + decode + correlate path without the agent. Shipped as `labs/fixtures/wazuh-sshd-fail.json`.

  Target: 27 checks total (21 inherited + 6 new).

---

## 4. Verification gate

Reset DB, regenerate OpenAPI + TS types. All must pass in order:

1. **Ingest refactor regression:** `docker compose up -d` (no wazuh profile). `smoke_test_phase7.sh` green. `/v1/wazuh/status.enabled == false`. Frontend badge shows gray "Bridge off". Proves the §3a pipeline extract broke nothing.
2. **Profile up, bridge on:** `docker compose --profile wazuh up -d` with `.env` exporting `WAZUH_BRIDGE_ENABLED=true` and the password. Backend logs show no tracebacks. Within ~30 s, `/v1/wazuh/status.reachable == true`, badge turns green.
3. **Resilience — indexer down:** `docker compose stop wazuh-indexer`. Within 3× poll interval, status `reachable=false, last_error=<message>`, badge amber with tooltip. Other endpoints remain 200. `smoke_test_phase7.sh` still green under this condition.
4. **Resilience — indexer up again:** `docker compose start wazuh-indexer`. Badge returns green without backend restart. Cursor resumes from stored `search_after` (verified via post-smoke log).
5. **End-to-end smoke:** `smoke_test_phase8.sh` green — all 27 checks.
6. **Browser flow:** `docker compose exec lab-debian` ssh fail-burst-then-success → `identity_compromise` incident in `/incidents` within ~10 s. Detail page shows events with `source=wazuh` (`agent.name=lab-debian`); raw Wazuh alert JSON visible in event detail; `T1110` (brute force) ATT&CK row rendered if part of the Phase 6 catalog.
7. **RAM sanity:** `docker stats` aggregates under full `--profile wazuh` stay well below 10 GB total (Tier A+B budget, ADR-0003). Expected rough breakdown: postgres ~0.3, redis ~0.1, backend ~0.5, frontend ~0.3, wazuh-indexer ~1.3 (capped heap + overhead), wazuh-manager ~1.5, lab-debian ~0.15 — total ~4.2 GB. Substantial headroom for OS + browser + IDE.
8. **Typecheck:** `npm run typecheck` clean. Generated `api.generated.ts` includes `Paths["/v1/wazuh/status"]` types.

Only when 1–8 pass, flip `PROJECT_STATE.md` Phase 8 to complete.

---

## 5. Out of scope (explicit)

| Item | Deferred to |
|---|---|
| Active Response wiring (isolate_host, kill_process, reset_session, block_observable, collect_evidence) | Phase 9 |
| Windows (Sysmon) lab endpoint + Sysmon `process.created` decoder branch | Phase 9 |
| Wazuh dashboard service | Never (CyberCat UI replaces it) |
| Per-agent enrollment UI inside CyberCat | Post-v1 |
| `cybercat_reader` role provisioning in indexer (replaces `admin`) | Phase 9 |
| CA pinning for the indexer TLS | Phase 9 |
| Historical backfill > `WAZUH_FIRST_RUN_LOOKBACK_MINUTES` | Phase 9+ if demand emerges |
| Alert throttling / rate limiting | Post-v1 |
| Auth on the product API (login, sessions) | Post-v1 |

---

## 6. Critical files — new and modified

**New:**
- `backend/app/ingest/pipeline.py` — shared ingest helper called from both the router and the poller.
- `backend/app/ingest/wazuh_decoder.py` — alert → normalized mapping.
- `backend/app/ingest/wazuh_poller.py` — poller loop + query builder.
- `backend/app/api/routers/wazuh.py` — `GET /v1/wazuh/status`.
- `backend/alembic/versions/0004_add_wazuh_cursor.py` — cursor table.
- `backend/tests/unit/test_wazuh_decoder.py` + `backend/tests/fixtures/wazuh/*.json` (three fixtures).
- `backend/tests/integration/test_wazuh_poller.py`.
- `labs/smoke_test_phase8.sh` + `labs/fixtures/wazuh-sshd-fail.json` (smoke-test fallback fixture).
- `infra/lab-debian/Dockerfile` — Debian 12 slim + sshd + auditd + Wazuh agent.
- `infra/lab-debian/entrypoint.sh` — auditd + agent enrollment + sshd bootstrap.
- `frontend/app/components/WazuhBridgeBadge.tsx`.
- `docs/decisions/ADR-0004-wazuh-bridge.md`.
- `docs/scenarios/wazuh-ssh-brute-force.md` — container-based end-to-end recipe.

**Modified:**
- `backend/app/main.py` — lifespan registers poller task; include `wazuh` router.
- `backend/app/config.py` — nine new env fields.
- `backend/app/db/models.py` — `WazuhCursor` model.
- `backend/app/api/routers/events.py` — replace inlined pipeline (lines 49–79) with helper call.
- `infra/compose/docker-compose.yml` — `wazuh-indexer`, `wazuh-manager`, and `lab-debian` services under `profiles: [wazuh]`.
- `docs/runbook.md` — replace `(TBI — Phase 8)` block at lines 99–105.
- `docs/architecture.md` §3.1 — update the Wazuh adapter line from "mechanism TBD in ADR-0004" to a short summary pointing at ADR-0004.
- `backend/openapi.json` + `frontend/app/lib/api.generated.ts` — regenerated; committed together.
- `PROJECT_STATE.md` — flip Phase 8 to complete; note Phase 9 as "response side-effects + security hardening."

**Reused (no edits — reference only):**
- `backend/app/ingest/normalizer.py` — validates the `normalized` dict; the decoder must emit shapes it accepts.
- `backend/app/ingest/entity_extractor.py` — unchanged; entity extraction is source-agnostic.
- `backend/app/correlation/rules/*.py` — all three correlators fire on Wazuh-sourced detections with zero changes (they key on `user + time` and detection `rule_id`, not `event.source`).
- `backend/app/detection/sigma/loader_registration.py` — Sigma rules match against `Event.normalized`, which is source-agnostic; Wazuh-sourced events fire Sigma rules automatically.
- `frontend/app/lib/usePolling.ts`, `frontend/app/components/StatusPill.tsx`, `RelativeTime.tsx` — reused in the bridge badge.
- `backend/app/api/schemas/errors.py` — `ErrorEnvelope` applied to the new router.

---

## 7. Risks and mitigations

1. **Self-signed TLS breaks httpx verification.** Mitigation: `WAZUH_INDEXER_VERIFY_TLS=false` default; explicit `httpx.AsyncClient(verify=False)`; ADR-0004 documents the debt; `# TODO Phase 9: CA pinning` comment at the call site.
2. **Indexer heap blows the budget.** Mitigation: force `-Xms1g -Xmx1g` via `OPENSEARCH_JAVA_OPTS`. Skipping the dashboard recovers ~700 MB. Using `lab-debian` as a container rather than a VM saves another ~1.3 GB. Verified target is ~4.2 GB total — well inside the 10 GB ceiling.
3. **Cursor corruption on clock skew.** Mitigation: cursor is `(timestamp, _id)` via OpenSearch `search_after`; `_id` is lexically deterministic and breaks ties cleanly.
4. **First-run flood.** Mitigation: `WAZUH_FIRST_RUN_LOOKBACK_MINUTES=5` default. Operator explicitly extends for intentional backfill.
5. **5 s poll cadence + 100 batch = ~20 alerts/sec ceiling.** Mitigation: §3d drain mode keeps looping without sleeping when a tick returns a full batch, so sustained bursts are bounded by RTT not interval. Documented in runbook.
6. **Decoder exception wedges the cursor.** Mitigation: per-alert `try/except`; drops increment the counter + log; cursor always advances to the batch's last `sort` tuple regardless of decode success per alert.
7. **Agent enrollment friction.** Mitigation: `lab-debian` entrypoint auto-enrolls against `wazuh-manager` on every boot using `WAZUH_REGISTRATION_PASSWORD`; no manual `manage_agents` dance, no operator SSH into a VM. `depends_on: wazuh-manager: service_healthy` ensures the manager is ready before enrollment attempts.
8. **Poller task silently dies.** Mitigation: `last_poll_at` staleness is surfaced via `/v1/wazuh/status` and the UI badge turns amber. Backoff loop never exits — a wedged task shows up immediately.
9. **DB session held across `asyncio.sleep`.** Mitigation: §3d explicitly opens a fresh session per tick; never holds across the interval sleep. Tested in integration test `(iv)` (unreachable → reachable) ensures no session leak.
10. **Two poller instances running (accidental scale-up).** Mitigation: single-row cursor with last-write-wins is tolerant, but the whitelist filter + dedup unique constraint means duplicate ingest is a no-op. Documented; not a correctness bug.
11. **Wazuh alert shape drift between versions.** Mitigation: pin `4.9.2`; decoder is a small mapping file; unit tests are JSON-fixture-based and catch drift on upgrade.
12. **auditd inside a container needs kernel audit access.** Mitigation: `lab-debian` runs with `CAP_AUDIT_WRITE` + `CAP_AUDIT_CONTROL` (or `privileged: true` as a simpler fallback for lab use). Documented in the scenario doc. If auditd/EXECVE can't initialize, sshd still emits auth events and the identity_compromise path still works — only the `process.created` branch of the demo is lost, and the smoke test's process-creation path can use the curl-fixture fallback.

---

## 8. Handoff note for Phase 9

Phase 8 leaves Phase 9 in excellent shape. Three threads:

- **Response side-effects.** The five handlers in `backend/app/response/handlers/stubs.py` (`isolate_host`, `kill_process`, `reset_session`, `block_observable`, `collect_evidence`) become real calls into Wazuh's Active Response API on manager port 55000. Auth uses the manager API user. Per-handler AR scripts are shipped to agents via the manager's `etc/shared/` config. Return/timeout semantics already captured in `action_logs`.
- **Security hardening.** Provision `cybercat_reader` role via `internal_users.yml` + `roles_mapping.yml`; pin the manager-generated CA bundle; flip `WAZUH_INDEXER_VERIFY_TLS=true` default.
- **Windows lab.** Phase 8's decoder has `process.created` covered for auditd; Phase 9 adds the Sysmon branch (`rule.groups` ⊇ `{sysmon_event1}`) mapping `data.win.eventdata.image/commandLine/parentImage`. Windows can ship as either a `lab-win10` Windows container (if Docker Desktop Windows-container mode is available) or a true VirtualBox/Hyper-V VM when the story needs it. The pipeline helper extracted in §3a makes the decoder addition a one-file change.

ADR-0005 (indexer role-based auth), ADR-0006 (Active Response handler registry) slot in naturally.

---

## Verification — how to test the plan (post-implementation)

1. From clean state: `docker compose down -v && docker compose up -d`; confirm Phase 7 smoke (21 checks) still green.
2. `docker compose --profile wazuh up -d`; wait for indexer health; confirm `/v1/wazuh/status` becomes `reachable=true`.
3. Run `labs/smoke_test_phase8.sh`; all 27 checks green.
4. Lab container scenario: follow `docs/scenarios/wazuh-ssh-brute-force.md` (all `docker compose exec lab-debian` steps — no VM needed); within ~10 s of the successful login, a new `identity_compromise` incident with Wazuh-sourced events (`agent.name=lab-debian`) appears in the UI.
5. Resilience: `docker compose stop wazuh-indexer`; badge amber; other routes still 200; `docker compose start wazuh-indexer`; badge green; no backend restart.
6. Typecheck: `cd frontend && npm run typecheck` exits 0; `api.generated.ts` contains `/v1/wazuh/status` types.
7. RAM: `docker stats` under full profile stays under 10 GB total.
