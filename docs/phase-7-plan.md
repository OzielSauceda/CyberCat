# Phase 7 Execution Plan — Detection Engineering + Standalone Endpoint + Codegen

Written 2026-04-21. Picks up after Phase 6 (full identity→endpoint chain verified, `smoke_test_phase6.sh` green, `tsc --noEmit` exits 0).

Read this first, then `PROJECT_STATE.md`, then `docs/architecture.md` §3.3 (detection) and §3.4 (correlation), then `docs/api-contract.md` §5/6/7 for the surfaces this phase touches.

---

## Context

Phase 6 closed the identity→endpoint chain end-to-end: ATT&CK names render, entities are navigable, detections are filterable, lab assets have CRUD UI. The platform is demonstrable, but two credibility gaps remain before Phase 8 (Wazuh bridge):

1. **All detections are Python if-statements.** The Project Brief explicitly flags detection-engineering credibility: *"I want the project to feel credible from a detection engineering perspective, not like arbitrary if-statements reacting to logs."* Phase 7 introduces Sigma as a first-class detection source so the platform has the vocabulary, parsing model, and rule-pack story Wazuh will plug into.
2. **Endpoint activity without prior identity priming is silent.** `endpoint_compromise_join` requires an open `identity_compromise` within 30 minutes; when none exists it returns `None` and the suspicious process event opens no incident — only a detection row nobody reads. Phase 7 adds a standalone `endpoint_compromise` correlator so every Phase 3/5/6 detector can open an investigable incident on its own.

Two developer-quality wins land alongside and pay off for the rest of v1:

- **OpenAPI → TS codegen** replaces ~250 lines of hand-written client types in `frontend/app/lib/api.ts` now that the API surface has stabilized (15 fetchers, 29 types). Phase 6 was the "does the surface still churn?" litmus — it didn't.
- **`/actions` top-level dashboard** — `GET /v1/responses` has been live since Phase 5 but unused by the UI; a single page turns it into a real response-history surface across all incidents.

Explicitly deferred to a Phase 7-tail (not this phase) or Phase 8:

- ATT&CK STIX pruner + ADR-0005 (data-only; no product risk; defer until we have a reason to expand beyond 24 entries).
- ADR-0006 merge semantics for multiple open identity_compromise incidents for one user (decision-only; no user pain today).
- Real quarantine/kill side effects (Phase 8 with Wazuh).

---

## 0. Why this phase matters

Phase 5 made response honest. Phase 6 made the chain visible. Phase 7 makes detection credible. Every "threat-informed" SOAR pitch-deck says the words "Sigma" and "ATT&CK" — without Sigma in the actual code, CyberCat is a custom rule engine wearing security clothes.

### Design principles that drive the differentiation

1. **Sigma is not a separate engine.** Loaded Sigma rules become `DetectionResult`-producing functions registered through the same `@register()` decorator as Python rules (`backend/app/detection/engine.py`). Detection persistence is unchanged; the only new thing is *how* the predicate is expressed. This keeps correlation, incident model, and frontend entirely untouched — the Sigma path is a data-source swap, not a parallel pipeline.
2. **Severity stratification tells the story.** Chained identity→endpoint stays at `high/0.80`. Standalone identity stays at `high/0.80`. Standalone endpoint lands at `medium/0.60`. The difference is itself the platform's editorial voice about evidence strength, and it renders automatically because the correlator owns it.
3. **Sigma and Python co-fire is a feature, not a bug.** When `py.process.suspicious_child` and `sigma-proc_creation_win_powershell_encoded_cmd` match the same event, both persist. The analyst sees *two engines converging* on the same evidence — a stronger signal than either alone. Correlator dedup (per incident) keeps the incident count honest.
4. **Join-first, standalone-second, never both.** The engine's first-non-None-wins short-circuit (`backend/app/correlation/engine.py:32-44`) gives us free ordering: register `endpoint_compromise_join` before `endpoint_compromise_standalone`, and the join wins whenever a user tie is found. No duplicate-incident risk, no hidden coupling.

---

## 1. Pre-work

### 1a. Schema audit

- `Detection.rule_source` already has `sigma` as a value (Phase 1 enum, confirmed `backend/app/enums.py:32`).
- `IncidentKind.endpoint_compromise` already exists (`backend/app/enums.py:46`).
- No new tables or columns. Sigma-specific metadata (rule file path, sigma id) rides in `Detection.matched_fields` (JSONB).
- **No new Alembic migration for schema.** Zero.

### 1b. Sigma rule selection (commit to repo)

Curate 6–8 rules from SigmaHQ that align to event kinds we already normalize. Rules are committed verbatim (attribution comment at the top of each file; we never auto-sync):

| Sigma rule (filename) | Target `event.kind` | What it catches |
|---|---|---|
| `proc_creation_win_powershell_encoded_cmd.yml` | `process.created` | Encoded PowerShell (overlaps with `py.process.suspicious_child` — deliberate; see §1c) |
| `proc_creation_win_office_spawn_shell.yml` | `process.created` | Office app spawns cmd/powershell/wscript |
| `proc_creation_win_rundll32_registered.yml` | `process.created` | Rundll32 loading unusual DLLs/exports |
| `proc_creation_win_lolbin_certutil_download.yml` | `process.created` | LOLBin — certutil used to fetch remote content |
| `proc_creation_win_lolbin_mshta_susp.yml` | `process.created` | LOLBin — mshta launching remote script |
| `logon_remote_explicit_credentials.yml` | `auth.succeeded` | Remote logon with explicit credentials (Type 10 / RunAs) |
| `network_connection_win_susp_outbound.yml` | `network.connection` | Outbound to known-suspicious port ranges |

Stored under `backend/app/detection/sigma_pack/` with a `pack.yml` manifest listing the active set. SigmaHQ updates are cherry-picked; never bulk-imported.

### 1c. Dedup between Python and Sigma rules

`proc_creation_win_powershell_encoded_cmd.yml` and `py.process.suspicious_child` both flag encoded-PS. Options considered:

- **Chosen:** let both fire. Each produces its own `Detection` row with distinct `rule_id`. Correlator dedup (by `dedup_key`) ensures they extend the same incident — no double-counting at the incident level. Duplicate detection rows are the intended shape: two engines converge.
- Rejected: suppress one. Too much orchestration, masks the signal, harder to explain in the UI.

### 1d. Standalone endpoint — dedup + severity convention

- Redis dedup key: `endpoint_compromise:{host_natural_key}:{hour_bucket}` (bucket = `%Y%m%d%H`, 2h TTL via SETNX).
- Severity: `medium`. Confidence: `Decimal("0.60")`.
- Rationale (templated): `"Endpoint signal observed on {host} without corroborating identity activity in the last 30 minutes."`
- Auto-actions: `tag_incident("endpoint-compromise-suspected")` only. No `elevate_severity` — we want the severity stratification visible in the UI, not normalized away.

### 1e. Sigma-sourced detection authorship

- `rule_id` = `sigma-<sigma_id>` (or slugified filename if no `id:`).
- `rule_source` = `DetectionRuleSource.sigma`.
- `rule_version` = `sha256(file_bytes)[:12]`.
- `severity_hint` ← Sigma `level:` (`low→low, medium→medium, high→high, critical→critical`).
- `confidence_hint` ← lookup from `level:` (`low 0.40, medium 0.60, high 0.70, critical 0.80`).
- `attack_tags` = Sigma `tags:` filtered to those starting with `attack.t`, normalized to `T####` / `T####.###`.
- `matched_fields` = `{"sigma_id": ..., "rule_title": ..., "pack_file": "<rel path>"}`.

---

## 2. Decisions locked

| Decision | Choice | Reason |
|---|---|---|
| Sigma module location | `backend/app/detection/sigma/` | Sits beside Python detectors under `detection/`; preserves the unified `@register()` API. |
| Sigma compiler | **In-house minimal interpreter** for the subset we use (selections + `condition` with AND/OR/NOT/`1 of`/`all of`, field modifiers `|contains`, `|endswith`, `|startswith`, `|re`, `|all`) | Full pySigma is heavy and tied to backend query outputs (ES/Splunk/etc.). We evaluate against our own `Event.normalized` dict — a thin evaluator is ~200 lines, typable, testable, and explainable. |
| Sigma load timing | At FastAPI startup via the existing lifespan — walk `sigma_pack/`, compile each, register via the existing decorator | No runtime reload; operators rebuild the image to pick up new rules. Matches the codebase's "no magic" ethos. |
| Unsupported Sigma constructs | Log a warning + skip the rule. `pack.yml` explicitly lists the active set so drift is loud. | Avoids silent correctness bugs. |
| Standalone endpoint correlator location | `backend/app/correlation/rules/endpoint_compromise_standalone.py` | Sibling to `endpoint_compromise_join.py`; pair reads "join if possible, else standalone." |
| Correlator ordering | `endpoint_compromise_join` registered first; `endpoint_compromise_standalone` second | `engine.run_correlators` returns on first non-None; join wins when user tie exists, standalone fires otherwise. |
| OpenAPI codegen tool | `openapi-typescript` (types-only) | Outputs a single `.d.ts`; zero client runtime imposed; preserves our hand-written thin fetchers. Alternatives (orval, hey-api) pull in client surface we'd have to integrate with. |
| Codegen trigger | `npm run gen:api` → hits `http://localhost:8000/openapi.json` → writes `frontend/app/lib/api.generated.ts`. Manual, not on-save. | Deterministic, reviewable diffs. |
| OpenAPI snapshot | `backend/openapi.json` committed + regenerated via `python -m scripts.dump_openapi`. Frontend can `gen:api:file` against it when backend isn't running. | Offline dev works; commit makes API-surface changes visible in PR diffs. |
| Error envelope in OpenAPI | Add `ErrorEnvelope` pydantic model; declare `responses={4xx: {"model": ErrorEnvelope}}` on every mutation endpoint | Generated TS gets a real error shape; removes the hand-written envelope parser's ambiguity. |
| `/actions` dashboard scope | List + filter (status, classification, kind, since) + click-through to incident. **No mutations from this page.** | Execute/Revert stay on incident detail where context is complete (Phase 5 principle #3). |
| Generated file commit policy | **Commit** `api.generated.ts` and `backend/openapi.json` | Makes API churn a reviewable diff; avoids "missing file → broken build" on fresh clone. Generated banner warns against hand-editing. |

---

## 3. Work plan (ordered — do not skip ahead)

### 3a. Typed error envelope (backend, do first — clears the codegen path)

- **New:** `backend/app/api/schemas/errors.py` with `ErrorDetail { code, message, details }` and `ErrorEnvelope { error: ErrorDetail }`.
- **Modify:** `incidents.py`, `responses.py`, `lab_assets.py`, `entities.py`, `detections.py`, `events.py` — declare `responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}}` on the endpoints that already raise those codes. Do not change the raise sites — `HTTPException(detail={"error": {...}})` remains the runtime shape.
- **Sanity check:** open `/docs`; confirm a 404 response on `GET /v1/incidents/{id}` shows `ErrorEnvelope` schema.

### 3b. Standalone endpoint correlator (backend)

**File:** `backend/app/correlation/rules/endpoint_compromise_standalone.py`

Behavior:
- Triggers on detections whose `rule_id` starts with `py.process.` or `sigma-proc_creation_`. Document this prefix convention in `docs/detection.md`.
- Registration order in `backend/app/correlation/__init__.py`: `identity_compromise`, `endpoint_compromise_join`, `endpoint_compromise_standalone`. The engine's first-non-None-wins logic gives us join-wins-over-standalone for free.
- Redis SETNX dedup key: `endpoint_compromise:{host_natural_key}:{hour_bucket}`, TTL 7200s.
- Opens `Incident(kind=endpoint_compromise, status=new, severity=medium, confidence=Decimal("0.60"))`.
- Junctions written: trigger event (role=`trigger`), trigger detection, host entity, IncidentAttack rows derived from `detection.attack_tags`, initial `null → new` transition with actor `system:correlator`.
- Rationale: `"Endpoint signal {rule_id} on host {host} without corroborating identity activity in the last 30 minutes."`

**Auto-actions:** add `IncidentKind.endpoint_compromise: [ActionProposal(kind=tag_incident, params={"tag": "endpoint-compromise-suspected"})]` in `backend/app/correlation/auto_actions.py::_AUTO_ACTIONS`. Reuse the existing `propose_and_execute_auto_actions` machinery — no new code there.

**Tests (`backend/tests/integration/test_endpoint_standalone.py`):**
1. Post `process.created` (encoded PS, alice@lab-win10-01) with no prior events → assert one `endpoint_compromise` incident, severity `medium`.
2. Repeat the same post within the same hour → no second incident (dedup holds).
3. Post 4×auth.failed + 1×auth.succeeded + 1×process.created → assert one `identity_compromise` incident, no `endpoint_compromise` (join wins).

### 3c. Sigma compiler + loader (backend — biggest chunk)

**New modules under `backend/app/detection/sigma/`:**

- `parser.py` — `SigmaRuleSpec(BaseModel)` matching SigmaHQ's YAML schema (fields: `id`, `title`, `description?`, `logsource {product?, category?, service?}`, `detection {<named selections>, condition}`, `level`, `tags?`). `parse_yaml(raw: str) -> SigmaRuleSpec`.
- `field_map.py` — single source of truth mapping Sigma field names to `Event.normalized` paths:
  - `Image` → `normalized.image`
  - `CommandLine` → `normalized.cmdline`
  - `ParentImage` → `normalized.parent_image`
  - `User` → `normalized.user`
  - `SourceIp` / `SrcIp` → `normalized.source_ip` / `normalized.src_ip`
  - `DestinationIp` / `DstIp` → `normalized.dst_ip`
  - `DestinationPort` / `DstPort` → `normalized.dst_port`
  - `LogonType` → `normalized.auth_type`
  - Plus `logsource.category` → `event.kind` table: `process_creation → process.created`, `authentication → auth.succeeded/auth.failed` (see `backend/app/ingest/normalizer.py` for the canonical kinds).
  - Anything not mapped → skip rule + warn.
- `compiler.py` — `compile_rule(spec: SigmaRuleSpec) -> CompiledRule`:
  - `CompiledRule` has `.logsource_match(event: Event) -> bool` (kind gate) and `.predicate_match(event: Event) -> bool` (selection+condition evaluator).
  - Evaluator supports `|contains`, `|endswith`, `|startswith`, `|re`, `|all`. Any other modifier → raise `UnsupportedSigmaConstruct` at compile time; the loader catches + warns + skips.
  - Condition grammar: `AND`, `OR`, `NOT`, `1 of selection_*`, `all of selection_*`. Implemented as a small recursive descent evaluator.
- `loader_registration.py` — `load_pack(pack_dir: Path) -> int`:
  - Reads `pack_dir / "pack.yml"` to get the active filename list (ignores files not in the manifest → lets us stash examples).
  - For each rule: parse → compile → wrap as `async def sigma_<slug>(event, db, redis): ...` returning `[DetectionResult]` when match, `[]` otherwise → call `detection.engine.register(sigma_<slug>)`.
  - Returns the count registered; logger logs a one-line summary at startup.
- `__init__.py` — re-exports `load_pack` for the main app.

**Wire-up:**
- `backend/app/detection/__init__.py` — after existing Python detector imports, call `from app.detection.sigma.loader_registration import load_pack` and invoke it with `Path(__file__).parent / "sigma_pack"`. Alternative: invoke from `main.py` lifespan — prefer `__init__.py` so test fixtures that import `app.detection` pick up Sigma too.
- `backend/pyproject.toml` + `backend/Dockerfile` — add `pyyaml>=6.0` if not already there.

**Pack:**
- `backend/app/detection/sigma_pack/pack.yml` — top-level `rules: [filename, ...]`.
- `backend/app/detection/sigma_pack/*.yml` — 6–8 curated rules from §1b, each with the SigmaHQ attribution header prepended.

**Tests:**
- `backend/tests/unit/test_sigma_parser.py` — parse + reject known bad shapes.
- `backend/tests/unit/test_sigma_compiler.py` — each modifier + each condition combinator; one unsupported-construct path.
- `backend/tests/unit/test_sigma_field_map.py` — mapping round-trip.
- `backend/tests/integration/test_sigma_fires.py` — post a synthetic encoded-PS event; assert the Sigma rule fires alongside `py.process.suspicious_child`; assert matched `sigma_id` in `Detection.matched_fields`.

**Docs:** `docs/detection.md` — short README covering: the pack manifest, the field map, the compiler subset, how to add a rule, attribution policy, the "Sigma + Python co-fire is a feature" explainer.

### 3d. OpenAPI codegen + api.ts refactor (frontend)

**Backend helper:**
- `backend/scripts/dump_openapi.py` — imports the app and writes `backend/openapi.json`. Run via `docker compose exec backend python -m scripts.dump_openapi`. Commit the resulting file.

**Frontend wiring:**
- `frontend/package.json` — add `"openapi-typescript": "^7.x"` to devDependencies; add scripts:
  - `"gen:api": "openapi-typescript http://localhost:8000/openapi.json -o app/lib/api.generated.ts"`
  - `"gen:api:file": "openapi-typescript ../backend/openapi.json -o app/lib/api.generated.ts"`
- Run `gen:api:file` to produce the initial `api.generated.ts`. Add the generated-file banner (if `openapi-typescript` doesn't emit one, prepend via a tiny wrapper).

**`frontend/app/lib/api.ts` refactor:**
- Replace each hand-written response type with a named re-export referencing `paths[...]["responses"]["200"]["content"]["application/json"]`. Keep existing export names so call sites don't churn (`IncidentList`, `IncidentDetail`, `EntityDetail`, `ActionSummary`, etc.).
- Keep all 15 fetcher functions; their return-type annotations swap to the generated types.
- Replace the hand-rolled error parser with a narrowing helper on the generated `ErrorEnvelope` shape.
- Delete the shadow enum unions (`IncidentStatus`, `Severity`, etc. — they now come from the generated spec).

**Verify:** `npx tsc --noEmit` exits 0. Incidents list, detail, actions panel, lab, entities, detections, attack all still render.

### 3e. `/actions` top-level dashboard (frontend)

**File:** `frontend/app/actions/page.tsx`

**Data:** `GET /v1/responses?status=&classification=&kind=&since=&limit=&cursor=`

*Backend-side check during implementation:* the `since` param may not exist on `responses.py` today (only Phase 5 scope had `incident_id`/`status`/`classification`). If missing, add it (small router-side addition; mirrors `/detections`). Grep during coding to confirm.

**UI:**
- Filter chips row: status (proposed/executed/failed/skipped/reverted/all), classification (auto_safe/suggest_only/reversible/disruptive/all), kind select with all 8 `ActionKind` values, since dropdown (1h/24h/7d/all).
- Table rows: `ActionClassificationBadge` + kind label + `StatusPill` (action-status variant — reuse or extend) + `proposed_by` chip + `RelativeTime(proposed_at)` + target entity (from `params`) + link to `/incidents/{incident_id}`.
- Load-more pagination mirroring `/detections` (cursor-based).
- Empty state + error state — reuse existing `EmptyState` / `ErrorState`.

**Nav:** add `Actions` link in `frontend/app/layout.tsx` between `Detections` and `Lab`.

**Non-goals:** no Execute/Revert on this page. Those stay on incident detail where the surrounding evidence context is complete.

### 3f. Smoke test `labs/smoke_test_phase7.sh`

Source `labs/smoke_test_phase6.sh` to inherit its 15 checks. Add:

1. `GET /openapi.json` → `.info.title == "CyberCat"` (sanity check spec is live before codegen runs).
2. Standalone endpoint: truncate DB, post `process.created` (encoded PS, alice@lab-win10-01) with **no prior auth events** → assert one `Incident` with `kind=endpoint_compromise`, `severity=medium`, `confidence=0.60`.
3. Standalone dedup: re-post the same process event inside the hour bucket → assert still one incident (no second).
4. Chain precedence: truncate, post 4×auth.failed + 1×auth.succeeded + 1×process.created → assert one `identity_compromise` incident (standalone correlator correctly skipped).
5. Sigma fire: post a `process.created` matching `proc_creation_win_powershell_encoded_cmd.yml` → assert ≥1 `Detection` with `rule_source=sigma` and the expected `sigma_id` in `matched_fields`.
6. Sigma+Python co-fire: same event → assert both `rule_source=py` and `rule_source=sigma` detection rows exist against the incident.

Target: 21 checks total (15 inherited + 6 new).

---

## 4. Verification gate

Reset DB (`docker compose down -v && docker compose up -d`) before starting. All must pass:

1. `npm run typecheck` clean in `frontend/`. Zero `any` introduced. `api.generated.ts` and `backend/openapi.json` are committed.
2. `pytest backend/` green. New unit tests for Sigma parser / compiler / field map. New integration tests for standalone endpoint (3 scenarios) and Sigma fire.
3. `labs/smoke_test_phase7.sh` runs green end-to-end (21 checks).
4. Browser flow (fresh DB):
   - Run the Phase 6 scenario → confirm chain incident opens as before. On the detail page, confirm both Sigma and Python detection rows render side-by-side with visible `rule_source=sigma` vs `rule_source=py`.
   - Post a lone `process.created` via `/docs` → confirm `endpoint_compromise` incident appears at `medium` severity. Click through: rationale sentence matches the templated string; actions panel shows the `endpoint-compromise-suspected` auto-tag executed by `system:correlator`.
   - `/actions` → filter by `classification=auto_safe` → rows appear with click-through to incident; filter `kind=tag_incident` + `since=1h` narrows correctly.
   - `/detections` → filter `rule_source=sigma` → only Sigma rows render; click through routes to the correct incident.
5. Codegen loop: delete `frontend/app/lib/api.generated.ts`, run `npm run gen:api:file`, re-run `npx tsc --noEmit` → exits 0. Proves the loop is not a one-shot.
6. Error envelope check: hit `/docs`; any 404/409/422 response on a mutation endpoint shows `ErrorEnvelope` as the response schema.

Only when 1–6 pass, flip `PROJECT_STATE.md` Phase 7 to complete.

---

## 5. Out of scope for Phase 7 (deferred)

| Item | Deferred to |
|---|---|
| ATT&CK STIX pruner, catalog expansion beyond 24 entries, ADR-0005 | Phase 7-tail (data-only; no product risk) |
| ADR-0006 incident merge semantics for multiple open identity_compromise incidents for one user | Phase 7-tail |
| Real side effects on response actions (actual quarantine/kill) | Phase 8 (Wazuh bridge) |
| Wazuh adapter wiring (ADR-0004) | Phase 8 |
| Full Sigma surface (aggregation `count`, `timeframe`, `near` correlation) | Phase 8+ if Wazuh shape demands |
| Auth / login | Post-v1 |
| SSE / WebSocket push | Post-v1 |
| Per-detector enable/disable UI | Post-v1 |
| Executing actions from the `/actions` dashboard | Post-v1 (kept on detail page per Phase 5 principle #3) |

---

## 6. Critical files

**Backend (new):**
- `backend/app/api/schemas/errors.py`
- `backend/app/detection/sigma/__init__.py`
- `backend/app/detection/sigma/parser.py`
- `backend/app/detection/sigma/compiler.py`
- `backend/app/detection/sigma/field_map.py`
- `backend/app/detection/sigma/loader_registration.py`
- `backend/app/detection/sigma_pack/pack.yml`
- `backend/app/detection/sigma_pack/*.yml` (6–8 rules)
- `backend/app/correlation/rules/endpoint_compromise_standalone.py`
- `backend/scripts/dump_openapi.py`
- `backend/tests/unit/test_sigma_parser.py`
- `backend/tests/unit/test_sigma_compiler.py`
- `backend/tests/unit/test_sigma_field_map.py`
- `backend/tests/integration/test_endpoint_standalone.py`
- `backend/tests/integration/test_sigma_fires.py`
- `backend/openapi.json` (generated, committed)
- `labs/smoke_test_phase7.sh`
- `docs/detection.md`

**Backend (modified):**
- `backend/app/detection/__init__.py` — call `load_pack(...)` after Python detector imports (`backend/app/detection/__init__.py:1`).
- `backend/app/correlation/__init__.py` — import `endpoint_compromise_standalone` **after** `endpoint_compromise_join`.
- `backend/app/correlation/auto_actions.py` — add `IncidentKind.endpoint_compromise` entry to `_AUTO_ACTIONS` (file location per Explore: `auto_actions.py:13-18`).
- `backend/app/api/routers/*.py` — declare `responses={4xx: {"model": ErrorEnvelope}}` on endpoints that raise those codes.
- `backend/app/api/routers/responses.py` — add `since` query param if missing (mirror `/detections`).
- `backend/pyproject.toml`, `backend/Dockerfile` — add `pyyaml>=6.0`.

**Frontend (new):**
- `frontend/app/actions/page.tsx`
- `frontend/app/lib/api.generated.ts` (generated, committed)

**Frontend (modified):**
- `frontend/app/lib/api.ts` — reroute types through generated file; keep the 15 fetcher functions; replace error parser with typed narrowing.
- `frontend/app/layout.tsx` — add `Actions` nav link.
- `frontend/package.json` — add `openapi-typescript` devDep + `gen:api` / `gen:api:file` scripts.

**Reused (no edits needed — reference only):**
- `backend/app/detection/engine.py::register`, `DetectionResult` (Phase 3, `engine.py:18-26, 38-40`) — Sigma compiled rules register via this same decorator.
- `backend/app/correlation/engine.py::run_correlators` (`engine.py:32-44`) — first-non-None short-circuit gives us join-wins-standalone ordering for free.
- `backend/app/correlation/extend.py::extend_incident` — not needed for standalone; standalone always creates a fresh incident.
- `backend/app/correlation/auto_actions.py::propose_and_execute_auto_actions` — unchanged; only the `_AUTO_ACTIONS` registry grows.
- `backend/app/ingest/entity_extractor.py::extract_and_link_entities` — unchanged; Sigma doesn't alter entity extraction.
- Frontend `components/` — `ActionClassificationBadge`, `StatusPill`, `RelativeTime`, `EntityChip`, `EmptyState`, `ErrorState`, `Skeleton` all reused on `/actions`.
- Frontend `lib/usePolling.ts` — `/actions` reuses for 10s polling.

---

## 7. Risks and mitigations

- **Sigma compiler correctness.** Small subset, but bugs in field resolution can silently drop matches. *Mitigation:* unit test every modifier + combinator; smoke test asserts at least one canonical event fires each pack rule; any compile/load failure is logged with the rule filename at startup.
- **Sigma+Python detection-row inflation.** More rows per incident could clutter the UI. *Mitigation:* the UI already lists detections under the Detections panel with `rule_source` visible — analysts distinguish at a glance. Correlator dedup keeps incident count honest.
- **Standalone endpoint creating demo noise.** Every encoded-PS event opens an incident. *Mitigation:* severity `medium` + confidence `0.60` visually distinguish from chain cases. Phase 6 smoke test still opens exactly one incident because of join-first ordering. Redis hour-bucket dedup prevents storms.
- **OpenAPI codegen drift.** If a developer hand-edits `api.generated.ts`, next regen wipes it. *Mitigation:* generated-file banner at the top; `.ts` file is committed so diffs in PR make edits visible.
- **Committed `openapi.json` churn.** Every router change changes the snapshot. *Mitigation:* this is a feature — the PR diff makes API surface changes explicit and reviewable.
- **Startup cost.** Loading 6–8 Sigma rules at FastAPI startup — negligible today (<50ms), but worth watching if the pack ever grows past ~50 rules.
- **Windows + Docker + YAML encoding.** `pyyaml` defaults usually handle it, but explicit `encoding="utf-8"` on every `open()` avoids surprises on the operator's machine. Documented in `docs/detection.md`.
- **Error-envelope refactor blast radius.** Every error path in the client needs audit after the generated type lands. *Mitigation:* Phase 5 + Phase 6 smoke tests already exercise every error code (out_of_lab_scope, invalid_transition, reason_required, incident_not_found, action_not_proposed). Running both smoke tests after the refactor validates the error shape.
- **`rule_id` prefix coupling.** The standalone correlator triggers on rule_id prefixes (`py.process.`, `sigma-proc_creation_`). Adding a new rule with a different naming scheme would silently bypass it. *Mitigation:* document the convention in `docs/detection.md`; future add-ons either follow the convention or extend the trigger predicate explicitly.

---

## 8. Handoff note for Phase 8 (Wazuh bridge)

Phase 7 leaves Phase 8 in excellent shape:

- Sigma compiler already matches against `Event.normalized`. When the Wazuh adapter lands, it just has to write normalized events in our canonical shape — detection logic is unchanged. No Sigma rewiring required.
- Standalone endpoint incidents will naturally start opening from Wazuh-sourced process events without any new correlator code.
- OpenAPI codegen means adding Wazuh-facing endpoints (e.g., `/v1/wazuh/status`) gets frontend type coverage on regen — no duplicate type hand-maintenance.
- Typed error envelope means Wazuh-adapter errors (auth fails, ingest errors) slot into the same pattern the UI already handles.
- ADR-0004 (Wazuh bridge mechanism) + ADR-0005 (ATT&CK catalog) + ADR-0006 (merge semantics) are the three decision documents waiting — writable in Phase 7-tail once Phase 7 implementation stabilizes.
