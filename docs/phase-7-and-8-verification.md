# Phase 7 & Phase 8 Verification Guide

Written 2026-04-21. Honest, step-by-step walkthrough to re-verify both phases from scratch.

**Why this doc exists:** Phase 7 was previously marked complete based on partial evidence (unit tests green, a few curl checks). Today while starting Phase 8 verification we uncovered a chain of pre-existing bugs that prove the Phase 7 integration test suite and the Phase 7 smoke test never actually ran green end-to-end. That means:

- Phase 7 implementation is in place, but **full end-to-end verification was never completed**.
- Phase 8 implementation is in place, but **verification is still blocked** — the very first verification step (pytest) surfaced the Phase 7 bugs that have only just been patched, and no test/smoke-script has yet run cleanly on the fixed codebase.

This document restarts verification from a known baseline. Treat it as a ground-truth checklist, not a victory lap.

---

## Legend

- ✅ implemented **and** verified end-to-end today
- 🟡 implemented but **not yet verified** (needs a clean run)
- ⚠️  previously claimed as verified, but the evidence underneath doesn't hold — needs re-check
- ⛔ blocked — cannot run yet
- 📂 artifact exists on disk

---

## Environment prerequisites

All commands run in **WSL2 Ubuntu**, from the project root:

```bash
cd /mnt/c/Users/oziel/OneDrive/Desktop/CyberCat
```

Docker Desktop must be running with WSL2 integration enabled. Compose file lives at `infra/compose/docker-compose.yml`.

---

# PHASE 7

## What Phase 7 was supposed to implement

Source of truth: `docs/phase-7-plan.md`.

| Area | Deliverable |
|---|---|
| Detection engineering | Sigma compiler + loader, curated 6–8 rule pack, registered through the same `@register()` decorator Python rules use |
| Correlation | Standalone `endpoint_compromise` correlator (medium/0.60) so endpoint signals open incidents without needing prior identity events; "join wins over standalone" ordering |
| Frontend | `/actions` top-level dashboard (read-only); OpenAPI → TypeScript codegen via `openapi-typescript` replacing hand-written client types |
| API ergonomics | Typed `ErrorEnvelope` on mutation endpoints so codegen surfaces real error shapes |
| Verification | `labs/smoke_test_phase7.sh` with 21 checks (15 inherited from Phase 6 + 6 new) |

## Phase 7 artifact audit (what exists on disk)

| Artifact | Status |
|---|---|
| `backend/app/detection/sigma/parser.py`, `compiler.py`, `field_map.py`, `loader_registration.py` | 📂 |
| `backend/app/detection/sigma_pack/pack.yml` + 6–8 `.yml` rules | 📂 |
| `backend/app/correlation/rules/endpoint_compromise_standalone.py` | 📂 |
| `backend/app/correlation/rules/endpoint_compromise_join.py` | 📂 |
| `backend/app/api/schemas/errors.py` (ErrorEnvelope) | 📂 |
| `backend/scripts/dump_openapi.py` | 📂 |
| `backend/openapi.json` | 📂 **but stale** (timestamped before today's Phase 8 changes — no `/v1/wazuh/status`, no `/v1/events` GET) |
| `frontend/app/actions/page.tsx` | 📂 |
| `frontend/app/lib/api.generated.ts` | 📂 **but stale** (same reason) |
| `backend/tests/unit/test_sigma_{parser,compiler,field_map}.py` | 📂 (38 tests, all passing in isolation) |
| `backend/tests/integration/test_endpoint_standalone.py` | 📂 (had 3 bugs — fixed today, not re-run yet) |
| `backend/tests/integration/test_sigma_fires.py` | 📂 (had 2 bugs — fixed today, not re-run yet) |
| `labs/smoke_test_phase7.sh` | 📂 (missing-`raw`-field bug was fixed earlier; checks 17–21 never confirmed on fixed version) |

## Known defects found today (now patched)

These were silently broken since Phase 7 was declared "complete":

1. **`backend/tests/conftest.py`** truncated table `"transitions"` which doesn't exist; the real table is `"incident_transitions"`. Fixed.
2. **`backend/tests/conftest.py`** `client` fixture used `ASGITransport(app=app)` which bypasses FastAPI's lifespan, so `init_redis()` never ran and any handler hitting `get_redis()` raised `Redis client not initialised`. Added explicit `init_redis()` / `close_redis()` in the fixture. Fixed.
3. **`backend/tests/integration/test_endpoint_standalone.py`** POST bodies were missing the required `raw` field (422 from pydantic). Asserted `status_code == 202` on a route that returns 201. Fixed (3 tests).
4. **`backend/tests/integration/test_sigma_fires.py`** same missing-`raw` + wrong-status-code bugs. Fixed (2 tests).

The `labs/smoke_test_phase7.sh` missing-`raw` bug was fixed in an earlier session but checks 17–21 were never re-run to confirm the fix holds.

---

## Phase 7 verification steps

Run in order. Each step has an expected result and a failure sign.

### P7-0. Baseline: rebuild and start the core stack

```bash
cd infra/compose
docker compose build backend frontend
docker compose up -d
```

**Expected:** all four core containers end in `(healthy)` within ~20 s (`postgres`, `redis`, `backend`, `frontend`).
**Failure sign:** backend container exits. Check `docker compose logs backend` — usually an Alembic migration failure or a missing module.

### P7-1. Unit tests (Sigma parser/compiler/field-map)

```bash
docker compose exec backend pytest tests/unit/
```

**Expected:** `46 passed` (38 Sigma unit tests + 8 new Wazuh decoder unit tests).
**Failure sign:** any failure here means the Sigma compiler or Wazuh decoder regressed. Stop and diagnose before moving on.

### P7-2. Full pytest run (integration + unit) — **the real test of today's fixes**

```bash
docker compose exec backend pytest
```

**Expected:** `57 passed, 0 errors, 0 failures`.
**Failure sign:** this is the step that will reveal whether today's conftest and test-file patches actually work. If anything fails, stop and paste the short-test-summary-info block into the next session. Do **not** proceed past this step on a red pytest — the smoke test will just hide the underlying breakage.

### P7-3. Confirm `/v1/wazuh/status` works with bridge off

```bash
curl -s http://localhost:8000/v1/wazuh/status
```

**Expected:** `{"enabled":false,"reachable":false,"last_poll_at":null,"last_success_at":null,"lag_seconds":null,"events_ingested_total":0,"events_dropped_total":0,"last_error":null}`.
**Failure sign:** 404 (router not registered) or 500 (migration 0004 not applied — check `docker compose logs backend` for the Alembic upgrade line).

### P7-4. Regenerate OpenAPI snapshot + TS types

The on-disk `openapi.json` and `api.generated.ts` predate today's Phase 8 endpoints. Regenerate:

```bash
# Write openapi.json inside the container, copy to host
docker compose exec backend python -m scripts.dump_openapi
docker compose cp backend:/app/openapi.json ../../backend/openapi.json

# Regenerate TS types from the file
cd ../../frontend
npm run gen:api:file
npm run typecheck
cd ..
```

**Expected:** `tsc --noEmit` exits 0. `grep wazuh backend/openapi.json` shows `/v1/wazuh/status`. `grep wazuh frontend/app/lib/api.generated.ts` also shows it.
**Failure sign:** typecheck errors in `frontend/app/lib/api.ts` — means some hand-written type references broke. Diff `api.generated.ts` to see what changed.

### P7-5. Smoke test (21 checks)

```bash
cd infra/compose
docker compose up -d --build frontend   # rebuild frontend if needed
cd ../..
bash labs/smoke_test_phase7.sh
```

**Expected:** `Phase 7 smoke test complete — 21 checks passed.`
**Failure signs:**
- Checks 1–15 (Phase 6 regression) fail → the pipeline extraction broke existing behaviour.
- Checks 17–18 fail (standalone endpoint) → the standalone correlator isn't firing or Redis dedup is misconfigured.
- Check 19 fails → join-wins-over-standalone ordering is wrong.
- Checks 20–21 fail → Sigma rules aren't loading at startup (check backend logs for `load_pack` count).

### P7-6. Browser flow

Open `http://localhost:3000`.

| Check | Expected |
|---|---|
| `/incidents` loads | List renders; polling is active (DevTools → Network shows 10s requests) |
| Top-nav shows "Bridge off" pill (gray) | Phase 8 badge with bridge disabled |
| `/actions` loads | Filter chips (status/classification/kind/since) work; rows click through to `/incidents/{id}` |
| `/detections` filter `rule_source=sigma` | Only Sigma rows appear |
| `/lab` | Lab assets CRUD works |
| An incident detail page | Detection rows show both `py` and `sigma` sources when they co-fire |

**Failure sign:** any blank panel, any 404, any TypeError in the console.

### P7-7. Error envelope check via /docs

```
open http://localhost:8000/docs
```

Pick any mutation endpoint that can 404 (e.g., `POST /v1/incidents/{id}/transitions`). Expand the 404 response. **Expected:** schema shows `ErrorEnvelope` with nested `error: ErrorDetail`.

---

## Phase 7 evidence / status

| Item | Status | Evidence |
|---|---|---|
| Sigma compiler + loader implemented | ✅ | Files exist; 38 unit tests pass in isolation |
| Sigma rules load at startup | 🟡 | Not confirmed on fixed codebase post-refactor |
| Standalone endpoint correlator implemented | ✅ | File exists |
| Standalone endpoint fires end-to-end | ⚠️ | Integration test was broken since day one; never actually passed; fixed today but not yet re-run |
| Join-wins-over-standalone ordering | ⚠️ | Same — integration test was broken; never validated |
| `/actions` dashboard | ✅ | Route exists, renders (manually verified earlier) |
| OpenAPI → TS codegen | 🟡 | Tooling works; current `api.generated.ts` is **stale** (missing Phase 8 endpoints) |
| ErrorEnvelope on mutation endpoints | ✅ | Schema declared on routers |
| 38 Sigma unit tests | ✅ | Last confirmed today |
| 5 Phase 7 integration tests | ⚠️→🟡 | Broken since creation; patched today; not yet re-run |
| Smoke test checks 1–15 (Phase 6 regression) | ✅ | Ran green last on 2026-04-21 before the pipeline refactor |
| Smoke test checks 17–21 (Phase 7) | ⚠️ | Previously "believed fixed"; never confirmed. Must re-run after P7-2 passes |
| `tsc --noEmit` clean | 🟡 | Was green against stale `api.generated.ts`; must re-run after regen |

**Honest summary:** The Phase 7 *implementation* is real, but the *verification* record was overstated. Until P7-2 and P7-5 come back green on today's patched test suite, treat Phase 7 as "implementation in place, verification pending."

---

# PHASE 8

## What Phase 8 was supposed to implement

Source of truth: `docs/phase-8-plan.md`.

| Area | Deliverable |
|---|---|
| Ingest pipeline refactor | Extract the router's dedup → detect → correlate → auto-action chain into `backend/app/ingest/pipeline.py` so both HTTP and poller share one code path |
| Wazuh poller | Asyncio pull-mode poller inside FastAPI process; queries Wazuh Indexer via OpenSearch `_search` + `search_after` cursor; cursor state persisted in `wazuh_cursor` Postgres table |
| Wazuh decoder | Map Wazuh alerts → normalized events (auth.failed, auth.succeeded, process.created); drop anything outside the rule-group whitelist |
| Status API | `GET /v1/wazuh/status` (unauthenticated); reports enabled/reachable/lag/counts/errors |
| Lab endpoint | `lab-debian` container (Debian 12 slim + sshd + auditd + Wazuh agent 4.9.2); two seeded users (`realuser`, `baduser`) |
| Compose | `wazuh-indexer`, `wazuh-manager`, `lab-debian` under `profiles: [wazuh]`; dashboard deliberately omitted |
| Frontend | `WazuhBridgeBadge` in top-nav (gray/green/amber) |
| Migration | `0004_add_wazuh_cursor` adds singleton `wazuh_cursor` row |
| Docs | ADR-0004; scenario doc; runbook update; architecture.md §3.1 update |
| Tests | Unit tests (decoder, 8 checks); integration tests (query builder, 6 checks); smoke test `labs/smoke_test_phase8.sh` (27 checks = 21 inherited + 6 new) |

## Phase 8 artifact audit (what exists on disk)

| Artifact | Status |
|---|---|
| `backend/app/ingest/pipeline.py` | 📂 |
| `backend/app/ingest/wazuh_decoder.py` | 📂 |
| `backend/app/ingest/wazuh_poller.py` | 📂 |
| `backend/app/api/routers/wazuh.py` | 📂 |
| `backend/app/api/routers/events.py` — uses pipeline + `GET /v1/events` listing | 📂 |
| `backend/app/api/schemas/events.py` — `EventSummary` + `EventList` | 📂 |
| `backend/app/db/models.py` — `WazuhCursor` model | 📂 |
| `backend/alembic/versions/0004_add_wazuh_cursor.py` | 📂 (never applied to a live DB) |
| `backend/app/config.py` — 9 Wazuh env vars | 📂 |
| `backend/app/main.py` — lifespan task + router include | 📂 |
| `backend/pyproject.toml` — `httpx` in runtime deps | 📂 |
| `backend/tests/unit/test_wazuh_decoder.py` + 3 JSON fixtures | 📂 (8 tests — confirmed passing in last pytest run) |
| `backend/tests/integration/test_wazuh_poller.py` | 📂 (6 tests — confirmed passing in last pytest run) |
| `infra/compose/docker-compose.yml` — wazuh profile | 📂 (never started) |
| `infra/lab-debian/Dockerfile` + `entrypoint.sh` | 📂 (never built) |
| `frontend/app/components/WazuhBridgeBadge.tsx` | 📂 |
| `frontend/app/layout.tsx` — badge wired | 📂 |
| `docs/decisions/ADR-0004-wazuh-bridge.md` | 📂 |
| `docs/scenarios/wazuh-ssh-brute-force.md` | 📂 |
| `docs/runbook.md` — Wazuh section | 📂 |
| `docs/architecture.md` §3.1 — updated | 📂 |
| `labs/smoke_test_phase8.sh` | 📂 (never run) |
| `labs/fixtures/wazuh-sshd-fail.json` | 📂 |

## Phase 8 verification steps

### Part A — core refactor (can run now; does NOT need Wazuh)

These verify the pipeline extraction + the status endpoint didn't break the existing app. Start here.

#### P8-A1. Confirm pipeline refactor didn't break existing flow

Already covered by **P7-5** above. The Phase 7 smoke test runs through the entire ingest → detect → correlate → auto-action chain; if the pipeline extraction broke anything, checks 1–15 will fail.

**Expected:** 21 checks pass (same as Phase 7).
**Failure sign:** a Phase 6 regression check fails — means the `ingest_normalized_event` signature or behaviour doesn't match what the router expected.

#### P8-A2. Wazuh-bridge-off status endpoint

Already covered by **P7-3**. Must return `enabled:false`.

#### P8-A3. Wazuh-related unit + integration tests (no Wazuh required)

These are already included in the full `pytest` run (P7-2). Expected:

- `tests/unit/test_wazuh_decoder.py` → 8 passed (fixture-based, no Wazuh)
- `tests/integration/test_wazuh_poller.py` → 6 passed (builds query dicts in-process, no Wazuh)

#### P8-A4. Migration 0004 applied

```bash
docker compose exec postgres psql -U cybercat -d cybercat -c "\dt wazuh_cursor"
```

**Expected:** table `wazuh_cursor` listed.
**Failure sign:** `Did not find any relation` → migration didn't run. Check `docker compose logs backend | grep -i alembic`. Fix: `docker compose exec backend alembic upgrade head`.

#### P8-A5. Frontend badge visible in gray "Bridge off"

Already covered by **P7-6** (browser flow).

---

### Part B — full Wazuh bridge (currently ⛔ blocked, see below)

These require pulling ~2 GB of Wazuh images and booting the manager + indexer + agent. Cannot run until Part A is confirmed green, and has its own prerequisites (see blocker section).

#### P8-B1. Create `.env` for Wazuh profile

```bash
cd infra/compose

cat > .env <<EOF
WAZUH_BRIDGE_ENABLED=true
WAZUH_INDEXER_PASSWORD=SecretPassword123!
LAB_REALUSER_PASSWORD=lab123
WAZUH_REGISTRATION_PASSWORD=
EOF
```

Restart backend so it picks up the new env:

```bash
docker compose up -d backend
```

#### P8-B2. Bring up the Wazuh profile

```bash
docker compose --profile wazuh build lab-debian
docker compose --profile wazuh up -d
```

**Expected:** 4 new containers start: `wazuh-indexer`, `wazuh-manager`, `lab-debian` (plus the core stack).
Wait 90–120 seconds; the indexer needs to initialise OpenSearch.

```bash
docker compose --profile wazuh ps
```

**Expected:** `wazuh-indexer` shows `(healthy)`. `wazuh-manager` shows `Up`.
**Failure sign:** indexer stuck in `(health: starting)` past 3 minutes → almost always WSL2 `vm.max_map_count`. Fix: `wsl -u root sysctl -w vm.max_map_count=262144` from PowerShell, then `docker compose --profile wazuh restart wazuh-indexer`.

#### P8-B3. Read the agent enrollment password and restart lab-debian

```bash
docker compose --profile wazuh exec wazuh-manager cat /var/ossec/etc/authd.pass
```

Copy that value into `.env` as `WAZUH_REGISTRATION_PASSWORD=...`, then:

```bash
docker compose --profile wazuh restart lab-debian
sleep 30
docker compose --profile wazuh exec wazuh-manager /var/ossec/bin/agent_control -l
```

**Expected:** `lab-debian` listed as `Active`.
**Failure sign:** agent listed as `Never connected` → check `docker compose --profile wazuh logs lab-debian` for the `agent-auth` command output.

#### P8-B4. Bridge goes green

```bash
curl -s http://localhost:8000/v1/wazuh/status
```

**Expected within 15 s of the indexer healthy:** `"reachable":true`. UI badge turns green.
**Failure sign:** `"reachable":false` with `last_error` containing a connection refused or 401 — check the indexer URL and password.

#### P8-B5. Fire the scenario

```bash
docker compose --profile wazuh exec lab-debian bash -c '
  for i in 1 2 3 4; do
    sshpass -p wrong ssh -o StrictHostKeyChecking=no baduser@localhost true 2>/dev/null || true
  done
  sshpass -p lab123 ssh -o StrictHostKeyChecking=no realuser@localhost true
'
sleep 15
curl -s 'http://localhost:8000/v1/events?source=wazuh&kind=auth.failed'
curl -s 'http://localhost:8000/v1/incidents?kind=identity_compromise'
```

**Expected:** ≥4 `auth.failed` events with `source=wazuh`; one `identity_compromise` incident.

Open `http://localhost:3000/incidents` and drill in — should see `agent.name: "lab-debian"` in the raw alert JSON on each event.

#### P8-B6. Resilience

```bash
docker compose --profile wazuh stop wazuh-indexer
sleep 20
curl -s http://localhost:8000/v1/wazuh/status
```

**Expected:** `"reachable":false`, `last_error` populated. Badge amber. Other endpoints still 200.

```bash
docker compose --profile wazuh start wazuh-indexer
sleep 30
curl -s http://localhost:8000/v1/wazuh/status
```

**Expected:** `"reachable":true` again. No backend restart.

#### P8-B7. Full Phase 8 smoke test

```bash
bash labs/smoke_test_phase8.sh
```

**Expected:** 27/27 checks pass.

#### P8-B8. RAM sanity

```bash
docker stats --no-stream
```

**Expected:** total under 10 GB. Rough breakdown in the plan: postgres ~0.3, redis ~0.1, backend ~0.5, frontend ~0.3, wazuh-indexer ~1.3, wazuh-manager ~1.5, lab-debian ~0.15 → ~4.2 GB.

---

## Phase 8 evidence / status

| Item | Status | Evidence |
|---|---|---|
| `pipeline.py` extraction | 🟡 | File exists; refactor correct by inspection; but full regression not yet re-run on patched test suite |
| `wazuh_decoder.py` | ✅ (unit) | 8 unit tests passed in last run; integration coverage pending (requires real Wazuh) |
| `wazuh_poller.py` | 🟡 | `build_query()` unit-tested; loop behaviour never exercised against a real indexer |
| Migration 0004 | 🟡 | File exists; never applied to a live DB because backend has been restarted/rebuilt several times but no-one has verified the table actually gets created on the existing volume |
| `GET /v1/wazuh/status` | 🟡 | Endpoint implemented; works by inspection; not yet curl-verified end-to-end on the patched codebase |
| `GET /v1/events` listing | 🟡 | Added so smoke test 25 can query; never exercised |
| `docker-compose.yml` Wazuh services | 🟡 | Declared; never brought up |
| `infra/lab-debian/` image | 🟡 | Dockerfile + entrypoint written; never built |
| Frontend `WazuhBridgeBadge` | 🟡 | Component written; rendering with stale `api.generated.ts` (pre-wazuh types) — may still render because it reads types via its own interface, but needs confirmation after typecheck |
| ADR-0004 | ✅ | Written, complete |
| Scenario doc | ✅ | Written, complete |
| Phase 8 smoke test | ⛔ | Never run |
| Resilience (down/up) | ⛔ | Never tested |

---

## ⛔ Phase 8 blocker section

As of 2026-04-21 evening, the following is true:

**Immediate blocker (small):** `pytest` has not been re-run on the patched codebase. Last full run showed `52 passed, 3 failed, 2 errors` — all five attributable to Phase 7 bugs patched today. Until a clean run is observed, we do not actually know whether the fixes hold. **This is step P7-2 above; it takes 2 seconds and unblocks everything downstream.**

**Medium blocker (expected but unpredictable):** the Wazuh profile has never been started on this machine. First boot is where the following commonly fail:

1. **`vm.max_map_count` kernel setting** — OpenSearch refuses to boot if it's below 262144. WSL2 defaults are lower. Fix is a one-liner from elevated PowerShell but must be done once.
2. **Indexer image pull size** — ~1.5 GB; slow connection stalls the pull.
3. **Registration password flow** — the manager auto-generates the `authd.pass` on first boot; there's a two-step dance where you read it out and re-inject it into `.env`, then restart `lab-debian`. Documented in P8-B3 but unconfirmed.
4. **`cap_add: AUDIT_WRITE/AUDIT_CONTROL`** — may still not be enough on WSL2 kernels; auditd may fail to initialise inside the container. The scenario doc acknowledges this: if auditd doesn't work, sshd-based auth events still flow and the identity-compromise path still works. Only the `process.created`/auditd branch of the demo would be lost.

None of these are correctness bugs in Phase 8 code — they're infrastructure-bring-up friction. The code path through the poller + decoder + pipeline is fully exercisable once a live indexer is reachable.

**Known workaround if Wazuh bring-up proves painful:** the smoke test has a fallback (`labs/fixtures/wazuh-sshd-fail.json`) — inject a fixture alert directly into the indexer via `curl`, skipping the agent. Exercises pull + decode + correlate without needing a working agent or auditd. This lets you prove the bridge works even if the lab container is fighting you.

---

# Final honest status summary

## What's actually true right now

- **Phase 5, 6:** implemented and genuinely verified end-to-end (smoke tests green on earlier dates).
- **Phase 7:** implementation complete. Previously labelled "complete" in `PROJECT_STATE.md`, but today's work surfaced four bugs in the Phase 7 test/fixture scaffolding that prove the integration test suite and smoke-test checks 17–21 have **never** run green on the codebase as committed. All four bugs are patched; no verification has yet run on the patched version.
- **Phase 8:** implementation complete. Core refactor (pipeline extraction, status endpoint, migration) can be verified immediately via P7-2 and P7-5. Full Wazuh bridge verification is ⛔ blocked on Wazuh profile bring-up, which has never happened on this machine.

## Recommended next steps, in order

1. **Run `docker compose exec backend pytest`**. If it reports `57 passed`, Phase 7 and Phase 8-Part-A are verified in one shot.
2. **Regenerate OpenAPI + TS types** (P7-4). Commit the regenerated files.
3. **Run `bash labs/smoke_test_phase7.sh`**. This exercises the full pipeline refactor regression + Sigma + standalone endpoint end-to-end.
4. **Walk the browser flow** (P7-6). Visual confirmation of `/incidents`, `/actions`, `/detections`, `/lab`, and the "Bridge off" pill.
5. **Commit today's patches:** `backend/tests/conftest.py`, `backend/tests/integration/test_endpoint_standalone.py`, `backend/tests/integration/test_sigma_fires.py`, and the regenerated `backend/openapi.json` + `frontend/app/lib/api.generated.ts`.
6. **Decide on the Wazuh bring-up path.** If ready, set `vm.max_map_count`, create `.env`, then run P8-B1 through P8-B8. If not ready, flip `PROJECT_STATE.md` to "Phase 8 core verified (Part A); full bridge verification (Part B) deferred until demo prep."

---

## Quick-reference commands

Copy/paste block for when you come back to this.

```bash
# Baseline
cd /mnt/c/Users/oziel/OneDrive/Desktop/CyberCat/infra/compose
docker compose build backend
docker compose up -d

# Tests + smoke
docker compose exec backend pytest                # expect 57 passed
bash ../../labs/smoke_test_phase7.sh              # expect 21 checks

# OpenAPI regen
docker compose exec backend python -m scripts.dump_openapi
docker compose cp backend:/app/openapi.json ../../backend/openapi.json
( cd ../../frontend && npm run gen:api:file && npm run typecheck )

# Status endpoint
curl -s http://localhost:8000/v1/wazuh/status

# Wazuh profile (Part B)
docker compose --profile wazuh build lab-debian
docker compose --profile wazuh up -d
docker compose --profile wazuh ps
docker compose --profile wazuh exec wazuh-manager cat /var/ossec/etc/authd.pass
docker compose --profile wazuh exec wazuh-manager /var/ossec/bin/agent_control -l
bash ../../labs/smoke_test_phase8.sh
```
