# Phase 9 Plan — CyberCat

## Context

Phase 7 and Phase 8 Part A are verified (2026-04-22). The platform ingests → normalizes → detects → correlates → opens incidents → supports 3 real response actions (`tag_incident`, `elevate_severity`, `flag_host_in_lab`). Five response kinds still return `skipped` from `backend/app/response/handlers/stubs.py`. Wazuh ingestion is wired but runs without TLS verification and uses the built-in `admin` user; the compose file lacks the cert infrastructure the 4.9.x indexer requires (Phase 8 Part B blocker). Telemetry is Linux-only (auditd via lab-debian).

Phase 9 closes these gaps to deliver on the Project Brief's core mandates:
- **"Response is a first-class capability, not an afterthought"** — replacing 5 stub handlers with real product-shaped implementations.
- **"Connects identity signals to endpoint signals"** cross-platform — adding Windows/Sysmon as a parallel endpoint telemetry source.
- **"Serious, not a toy"** — flipping TLS verify on, scoping the indexer role to read-only.
- **"Threat-informed"** — growing the ATT&CK catalog to cover the techniques our detectors and scenarios plausibly touch.

Phase 8 Part B (cert infra) folds into Phase 9B since TLS hardening structurally depends on it.

---

## Shape

**Phase 9A — Response completeness + ATT&CK expansion.** App-layer only, zero Wazuh-infra dependency. Ships first.

**Phase 9B — Wazuh profile completion + cross-platform telemetry.** Absorbs Phase 8 Part B. Wazuh certs + TLS hardening + `cybercat_reader` role + Windows/Sysmon lab + Sysmon decoder branch. Ships after 9A verifies clean.

Rationale: 9A is the highest-product-value work (completes the response story end-to-end — the Brief's central resume point) and is fully verifiable on today's stack. 9B is infra-heavy and gated on Wazuh bring-up; doing it second means 9A never blocks on a cert-generation failure or a Windows-container surprise.

---

## Phase 9A — Response Completeness + ATT&CK Expansion

### Handler design principle

All five new handlers follow the existing real-handler pattern (`backend/app/response/handlers/flag_host_in_lab.py:12-44`, `elevate_severity.py:11-37`, `tag_incident.py:11-35`):
- `async def execute(action, db) → (ActionResult, reason?, reversal_info?)`
- `async def revert(action, db, log) → (ActionResult, reason?)` for reversible kinds only
- Register in `_EXECUTE` + `_REVERT` maps in `backend/app/response/executor.py:51-71`
- Add entry in `_SCOPE_CHECKS` (`executor.py:77-83`) where params reference lab assets
- Enable form in `frontend/app/lib/actionForms.ts:23-107`

**Core principle:** Every handler produces a **verifiable, product-meaningful state change** — not infra theater. The disruptive handlers (quarantine, kill_process) create workflow state in 9A; actual OS/network side-effects arrive in 9B via Wazuh Active Response. This sequence makes both phases independently valuable.

### Handler implementations

**1. `quarantine_host_lab`** — disruptive (no revert per `policy.py:9-42`)
- Mutates `LabAsset.notes` with `[quarantined:incident-{id}:at-{ts}]` marker
- Annotates the host entity with `status=quarantined` in metadata
- Adds a transition note on the incident: "Host {name} quarantined by action #{id}"
- Params: `host` (natural_key); lab-scope check required
- 9B extension point: dispatch Wazuh AR `firewall-drop` on the agent

**2. `kill_process_lab`** — disruptive (no revert)
- Logs the kill in `action_logs` with rich `reversal_info` (captured process state snapshot)
- Annotates the process `Entity` with `killed_at`, `killed_by_action_id`
- Auto-creates a follow-up `evidence_request` (kind=`process_list`) on the same host so the analyst can verify
- Params: `host` (lab asset), `pid`, `process_name`
- 9B extension: dispatch Wazuh AR `kill-process` or equivalent

**3. `invalidate_lab_session`** — reversible
- New table `lab_sessions` (see migration below)
- Sets `invalidated_at = now()` on matching row; `reversal_info` captures prior state
- Revert unsets `invalidated_at`
- Params: `user` (natural_key), `host` (natural_key)
- Normalizer extension: populate `lab_sessions` from `auth.succeeded` events so the handler always has a row to act on

**4. `block_observable`** — reversible
- New table `blocked_observables` (kind, value, active flag)
- Inserts active row on execute; revert flips `active=false`
- Params: `kind` (ip/domain/hash/file), `value`
- **Product integration bonus:** `backend/app/detection/engine.py` consults this table via a cached (Redis, 30s TTL) lookup; when a new event references a blocked observable, a `py.blocked_observable_match` detection fires. This makes the handler a real platform feature, not state tracking.
- No lab-scope check (observables are platform-global)

**5. `request_evidence`** — suggest_only (no revert)
- New table `evidence_requests` (incident_id, target_host, kind, status, collected_at, payload_url)
- Insert with `status=open`; analyst can mark `collected` or `dismissed` from UI
- Params: `target_host` (optional lab asset), `evidence_kind` (`triage_log` | `process_list` | `network_connections` | `memory_snapshot`)
- Auto-proposed by the correlator on identity_compromise incidents (`auto_actions.py`)

### Migration 0005 — `0005_response_state_tables.py`

Single Alembic migration creating:
- `lab_sessions` — (id, user_entity_id FK, host_entity_id FK, opened_at, invalidated_at nullable, invalidated_by_action_id FK nullable)
- `blocked_observables` — (id, kind enum, value, blocked_at, blocked_by_action_id FK, active bool indexed)
- `evidence_requests` — (id, incident_id FK, target_host_entity_id FK nullable, kind enum, status enum [open/collected/dismissed], requested_at, collected_at nullable, payload_url nullable)

Follows naming + upgrade/downgrade convention from `0004_add_wazuh_cursor.py`.

### Backend changes

- **NEW:** `backend/app/response/handlers/quarantine_host.py`, `kill_process.py`, `invalidate_session.py`, `block_observable.py`, `request_evidence.py`
- **DELETE:** `backend/app/response/handlers/stubs.py` (after moving references)
- **MODIFIED:** `backend/app/response/executor.py` — register 5 new handlers in `_EXECUTE` + `_REVERT`; add scope checks for kinds that touch lab assets
- **MODIFIED:** `backend/app/db/models.py` — 3 new SQLAlchemy models + relationships
- **MODIFIED:** `backend/app/correlation/auto_actions.py` (`auto_actions.py:13-21`) — propose `request_evidence` as suggest-only on identity_compromise incidents
- **MODIFIED:** `backend/app/detection/engine.py` — pre-ingest hook that checks normalized event fields against active `blocked_observables` (Redis-cached), fires `py.blocked_observable_match` detection
- **MODIFIED:** `backend/app/ingest/normalizer.py` or `entity_extractor.py` — populate `lab_sessions` rows on `auth.succeeded` events where both user and host exist as lab assets
- **MODIFIED:** `backend/app/api/routers/responses.py` — no schema change needed; existing propose/execute/revert endpoints cover all new kinds. Possibly add `/v1/evidence-requests` sub-router for analyst-side collected/dismissed transitions
- **MODIFIED:** `backend/app/api/schemas/` — new schemas for `EvidenceRequest`, `BlockedObservable`, `LabSession` so they appear on incident detail responses

### ATT&CK catalog expansion

- **MODIFIED:** `backend/app/attack/catalog.json` — grow from 24 to ~35 entries. No code changes needed (module-level load-once pattern in `catalog.py:25-40`).
- **New coverage targets** (selected so detectors + scenarios + UI chips all have valid IDs):
  - TA0003 Persistence: T1098 (account manipulation), T1547.001 (run keys), T1053.005 (scheduled tasks)
  - TA0004 Priv Esc: T1068 (exploitation for priv esc), T1134 (token manipulation)
  - TA0007 Discovery: T1057 (process discovery), T1087 (account discovery), T1018 (remote system discovery)
  - TA0011 C2: T1071.001 (web protocols), T1105 (ingress tool transfer)
  - Fill gaps in existing tactics where our Sigma pack fires but catalog lacks the entry

### Frontend changes

- **NEW:** `frontend/app/components/EvidenceRequestsPanel.tsx` — list of open/collected requests on incident detail page; mark collected/dismissed buttons
- **NEW:** `frontend/app/components/BlockedObservablesBadge.tsx` — small chip on entity detail showing "blocked" status with revert control
- **MODIFIED:** `frontend/app/lib/actionForms.ts:23-107` — enable all 5 kinds with proper fields:
  - `quarantine_host_lab`: host select (lab asset, kind=host)
  - `kill_process_lab`: host select + pid number + process_name text
  - `invalidate_lab_session`: user text + host select
  - `block_observable`: kind select + value text
  - `request_evidence`: host select optional + evidence_kind select
- **MODIFIED:** `frontend/app/incidents/[id]/page.tsx` — add `EvidenceRequestsPanel` below response actions
- **MODIFIED:** `frontend/app/entities/[id]/page.tsx` — show `BlockedObservablesBadge` when entity is an observable in the blocked list

### Tests

- **NEW:** `backend/tests/unit/test_handlers_real.py` — for each of 5 handlers: execute happy path, execute with lab-scope failure, revert happy path (reversible kinds), revert on non-executed action (must reject)
- **NEW:** `backend/tests/integration/test_response_flow_phase9.py` — propose → execute → revert end-to-end via API for each kind
- **NEW:** `backend/tests/integration/test_blocked_observable_detection.py` — block an IP, ingest an event referencing it, assert `py.blocked_observable_match` fires
- **NEW:** `backend/tests/integration/test_evidence_request_auto_propose.py` — identity_compromise incident → confirm `request_evidence` is proposed as suggest-only
- **MODIFIED:** `backend/tests/conftest.py` — `truncate_tables` includes the 3 new tables

### Smoke test

**NEW:** `labs/smoke_test_phase9a.sh` — ~14 checks:
1. OpenAPI lists all 8 `ActionKind` values as available handlers
2. `quarantine_host_lab`: propose + execute → `LabAsset.notes` contains marker
3. `kill_process_lab`: propose + execute → `action_logs` entry + auto-created `evidence_request`
4. `invalidate_lab_session`: propose + execute + revert → `invalidated_at` set then unset
5. `block_observable`: propose + execute → row in `blocked_observables` with `active=true`
6. Ingest event with blocked IP → `py.blocked_observable_match` detection fires
7. Revert `block_observable` → `active=false`, subsequent events no longer match
8. `request_evidence`: propose (analyst) → list via GET, mark collected → status flips
9. identity_compromise auto-proposes `request_evidence` (suggest_only)
10. ATT&CK catalog `GET /v1/attack/catalog` returns ≥35 entries
11. All 3 new migrations applied (`\dt lab_sessions`, etc.)
12. Non-existent lab asset: handler returns `skipped` with scope-failure reason
13. Revert on disruptive kind: API rejects with `400` + clear reason
14. Regression: previous real handlers (tag, elevate, flag_host) still work

Follows `smoke_test_phase7.sh` conventions (numbered `check` calls, color-coded PASS/FAIL, exit code from summary).

### ADR

**NEW:** `docs/decisions/ADR-0005-response-handler-shape.md` — captures the decision to make 9A handlers DB-state-focused (with 9B adding Active Response). Notes why disruptive handlers still produce visible product state (evidence_request follow-up, entity metadata) rather than returning `skipped` until AR is available.

### 9A verification (phase complete when)

- `docker compose exec backend pytest` → all tests pass (target ~70 passing; 57 baseline + ~13 new)
- `labs/smoke_test_phase9a.sh` → 14/14 pass
- `labs/smoke_test_phase7.sh` → 21/21 pass (regression)
- `labs/smoke_test_phase8.sh` → 27/27 pass (regression)
- OpenAPI regen + frontend `npm run typecheck` clean
- Browser: manually propose + execute each of 5 new action kinds from the UI; revert the reversible ones; confirm state in UI + pgcli

---

## Phase 9B — Wazuh Profile Completion + Cross-Platform Telemetry

### Sub-track 1: Cert infrastructure (absorbs Phase 8 Part B)

- **NEW:** `infra/compose/wazuh-config/generate-indexer-certs.yml` (copy from `wazuh/wazuh-docker@v4.9.2/single-node`)
- **NEW:** `infra/compose/wazuh-config/config/wazuh_indexer/wazuh_indexer.yml`, `internal_users.yml`, `roles.yml`, `roles_mapping.yml`
- **NEW:** `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf`
- **MODIFIED:** `infra/compose/docker-compose.yml` — add one-shot `cert-generator` service (runs once to populate `./config/wazuh_indexer_ssl_certs/`); add cert bind mounts on `wazuh-indexer` and `wazuh-manager` services
- **MODIFIED:** `docs/runbook.md` — Wazuh bring-up procedure: run cert-generator once, then `docker compose --profile wazuh up -d`
- Verification: indexer reaches `healthy` within 2 min; `curl -k https://localhost:9200 -u admin:...` returns cluster info

### Sub-track 2: TLS hardening + `cybercat_reader` role

- **MODIFIED:** `wazuh-config/internal_users.yml` — add `cybercat_reader` user with bcrypt-hashed password
- **MODIFIED:** `wazuh-config/roles.yml` + `roles_mapping.yml` — `cybercat_reader` role: `cluster_permissions: []`, `index_permissions: [{ index_patterns: ["wazuh-alerts-*"], allowed_actions: ["read", "search"] }]`
- **MODIFIED:** `backend/app/config.py:16-25`:
  - `WAZUH_INDEXER_USER` default → `"cybercat_reader"`
  - `WAZUH_INDEXER_VERIFY_TLS` default → `true`
  - NEW: `WAZUH_CA_BUNDLE_PATH` → `/etc/ssl/certs/wazuh-ca.pem`
- **MODIFIED:** `infra/compose/docker-compose.yml` backend service — mount the CA bundle from `./wazuh-config/config/wazuh_indexer_ssl_certs/root-ca.pem:/etc/ssl/certs/wazuh-ca.pem:ro`
- **MODIFIED:** `backend/app/ingest/wazuh_poller.py:58-62` — `verify=settings.wazuh_ca_bundle_path` when `wazuh_indexer_verify_tls` is true, else `False`
- Verification: `cybercat_reader` `_search` succeeds on `wazuh-alerts-*`, `_doc` PUT fails with 403; backend poller negotiates TLS against mounted CA

### Sub-track 3: Windows/Sysmon lab + decoder

- **NEW:** `infra/lab-windows/` — primary approach: Windows-nanoserver-based Dockerfile with Wazuh agent 4.9.2 + Sysmon installed with SwiftOnSecurity's sysmonconfig-export.xml. Fallback plan: document VirtualBox VM bring-up (Windows 10 eval ISO) in `docs/runbook.md` for environments where Windows containers aren't available. Reference pattern: `infra/lab-debian/Dockerfile`.
- **NEW:** `backend/tests/fixtures/wazuh-sysmon-benign.json`, `wazuh-sysmon-suspicious-child.json`, `wazuh-sysmon-encoded-pwsh.json` (real-shape Wazuh alerts with `data.win.eventdata.*` fields)
- **MODIFIED:** `backend/app/ingest/wazuh_decoder.py:11` — add `"sysmon_event1"` to `_WHITELIST`
- **MODIFIED:** `backend/app/ingest/wazuh_decoder.py:95-113` — add an `elif "sysmon_event1" in groups` branch after the auditd branch. Map:
  - `agent.name` → `host`
  - `data.win.eventdata.image` → `image`
  - `data.win.eventdata.commandLine` → `cmdline`
  - `data.win.eventdata.parentImage` → `parent_image`
  - `data.win.eventdata.processId` → `pid`
  - `data.win.eventdata.parentProcessId` → `ppid`
  - return kind `process.created`
- **MODIFIED:** `backend/app/ingest/wazuh_poller.py:29-34` — add `"sysmon_event1"` to the `rule.groups` filter
- **MODIFIED:** `backend/tests/unit/test_wazuh_decoder.py` — 3 new tests (one per fixture)

### ADR

- **NEW:** `docs/decisions/ADR-0006-wazuh-cert-infrastructure.md` — documents the cert infra, why the simplified no-certs shape failed at 4.9.x, TLS + reader-role hardening, Windows/Sysmon extension point
- **MODIFIED:** `docs/decisions/ADR-0004-wazuh-bridge.md` — addendum section pointing to ADR-0006, mark "Security debt" as resolved

### Scenario doc

**NEW:** `docs/scenarios/windows-suspicious-powershell.md` — step-by-step demo: lab-windows runs an encoded PowerShell command → Sysmon EID 1 → Wazuh → poller ingests → decoder normalizes to `process.created` → `py.process.suspicious_child` fires → correlator links to a concurrent identity_compromise if present. Format follows `docs/scenarios/wazuh-ssh-brute-force.md`.

### Smoke test

**NEW:** `labs/smoke_test_phase9b.sh`:
1. `wazuh-indexer` healthy (HTTP 200 on `/_cluster/health`)
2. `cybercat_reader` can GET `wazuh-alerts-*/_search`
3. `cybercat_reader` cannot PUT to any index (403 expected)
4. Backend poller authenticates with TLS verify=true (check logs for successful auth, no `SSLError`)
5. lab-windows agent registers with manager (visible in `agents list`)
6. Sysmon fixture injection → `events` table row with kind `process.created`, host matches Windows lab name
7. Encoded-PowerShell Sysmon event → `py.process.suspicious_child` detection fires
8. Combined flow: identity_compromise opened (via lab-debian SSH path) → Windows suspicious process (via lab-windows) within 30 min → `endpoint_compromise_join` correlator extends the incident with the Windows host
9. Regression: 9A smoke + Phase 7/8 smoke all green

### 9B verification (phase complete when)

- `docker compose --profile wazuh up -d` reaches healthy in <2 min on a clean tree
- `smoke_test_phase9b.sh` → all checks pass
- Negative tests pass: `cybercat_reader` write blocked, TLS verify rejects bad cert
- Sysmon event round-trips in under 30s (poller interval + processing)
- Browser: Windows host appears as an entity chip on an incident; ATT&CK tags display correctly

---

## Sequence

1. **Ship 9A** — handlers + migration + ATT&CK + tests + smoke + ADR-0005. ~3–5 sittings.
2. **Verify 9A** — full pytest + all smoke tests green + manual browser flow.
3. **Update `PROJECT_STATE.md`** — mark 9A complete honestly (per `CLAUDE.md` §8: "never mark work 'done' that wasn't actually verified").
4. **Start 9B sub-track 1** (cert infra) — get indexer booting before anything else.
5. **9B sub-track 2** (TLS + reader role) — layer security on top of working infra.
6. **9B sub-track 3** (Sysmon lab + decoder) — last because it depends on manager being up and reachable.
7. **Verify 9B** — smoke test + scenario doc walkthrough.

---

## Critical files reference

### 9A modifications
- Handlers (new): `backend/app/response/handlers/{quarantine_host,kill_process,invalidate_session,block_observable,request_evidence}.py`
- Existing handler pattern to match: `backend/app/response/handlers/flag_host_in_lab.py:12-44`
- Registry: `backend/app/response/executor.py:51-71`, scope checks at `:77-83`
- Policy (read-only reference): `backend/app/response/policy.py:9-42`
- Models: `backend/app/db/models.py` (Action at `:301-329`, ActionLog at `:336-353`, LabAsset at `:360-373` — add 3 new models following same pattern)
- Correlator auto-actions: `backend/app/correlation/auto_actions.py:13-21`
- Detection engine hook point: `backend/app/detection/engine.py` (pre-ingest blocked_observable check)
- Action forms: `frontend/app/lib/actionForms.ts:23-107`
- Incident detail: `frontend/app/incidents/[id]/page.tsx`
- Migration numbering: follows `backend/alembic/versions/0004_add_wazuh_cursor.py`
- Smoke convention: `labs/smoke_test_phase7.sh` (numbered `check` pattern)

### 9B modifications
- Decoder whitelist: `backend/app/ingest/wazuh_decoder.py:11`
- Decoder kind mapping: `backend/app/ingest/wazuh_decoder.py:95-113`
- Poller TLS + query: `backend/app/ingest/wazuh_poller.py:29-34`, `:58-62`
- Config: `backend/app/config.py:16-25`
- Compose: `infra/compose/docker-compose.yml` (wazuh profile block)
- Lab endpoint pattern: `infra/lab-debian/Dockerfile` + `entrypoint.sh`
- ADR precedent: `docs/decisions/ADR-0004-wazuh-bridge.md`
- Scenario precedent: `docs/scenarios/wazuh-ssh-brute-force.md`

---

## Risks to watch

- **Handler over-engineering.** Temptation to build 200-LOC handlers with complex state machines. Target: ≤80 LOC each, implementing only what `policy.py` classifies.
- **`block_observable` hot path.** Every ingested event consulting this table is a performance risk. Cache active observables in Redis with 30s TTL; invalidate on insert/revert.
- **Windows container runtime.** Docker Desktop on Windows supports Windows containers but Linux-mode doesn't. Decide early: Windows-container or VirtualBox VM. Don't half-commit.
- **Wazuh cert generator quirks.** The upstream `generate-indexer-certs.yml` expects a specific directory layout. Import the reference verbatim before simplifying.
- **ATT&CK coverage drift.** Resist growing the catalog to 100+. Keep ≤40 curated entries covering what the platform actually touches.
- **Verification theatre (from CLAUDE.md §8 and `PROJECT_STATE.md` "Risks").** Don't mark 9A or 9B complete until smoke + pytest + browser flow are all green on a clean checkout.

---

## Verification section (end-to-end test plan)

### Phase 9A

```bash
cd /mnt/c/Users/oziel/OneDrive/Desktop/CyberCat/infra/compose
docker compose build backend
docker compose up -d

# 1. Migration applies
docker compose exec backend alembic current  # expect 0005_...

# 2. Backend tests green
docker compose exec backend pytest
# expect ~70 passed, 0 failed

# 3. Phase 9A smoke
bash ../../labs/smoke_test_phase9a.sh
# expect: 14/14 pass

# 4. Regression
bash ../../labs/smoke_test_phase7.sh  # 21/21
bash ../../labs/smoke_test_phase8.sh  # 27/27

# 5. OpenAPI + frontend typecheck
docker compose exec backend python -m scripts.dump_openapi
docker compose cp backend:/app/openapi.json ../../backend/openapi.json
( cd ../../frontend && npm run gen:api:file && npm run typecheck )

# 6. Browser flow: http://localhost:3000/incidents/{id}
#    - Propose + execute each of 5 new action kinds
#    - Revert invalidate_lab_session and block_observable
#    - Verify EvidenceRequestsPanel renders open/collected/dismissed states
#    - Confirm ATT&CK chips render for newly added technique IDs
```

### Phase 9B

```bash
# Cert generation (one-time)
docker compose -f docker-compose.yml -f wazuh-config/generate-indexer-certs.yml run --rm generator

# Bring up Wazuh profile
docker compose --profile wazuh up -d

# Wait for indexer healthy, then:
bash ../../labs/smoke_test_phase9b.sh
# expect: all checks pass including cybercat_reader negative test

# Demo scenario walkthrough
cat ../../docs/scenarios/windows-suspicious-powershell.md
# follow steps 1-5, confirm Windows host appears as entity on incident
```

---

## Completion criteria

**Phase 9A complete** when pytest green + 9A smoke green + Phase 7/8 regression green + browser flow confirmed + `PROJECT_STATE.md` updated honestly.

**Phase 9B complete** when Wazuh profile reaches healthy in <2 min + `cybercat_reader` least-privilege enforced + TLS verify=true end-to-end + Sysmon event round-trips + 9B smoke green + `PROJECT_STATE.md` marks all Phase 9 items done + ADR-0006 merged.

After Phase 9B, the platform delivers the Brief's full end-to-end demo: upstream Wazuh telemetry → correlation into incidents → ATT&CK context → real response actions (including network-level containment via AR extension points) → reversible state transitions → analyst visibility. This is the resume-defining milestone.
