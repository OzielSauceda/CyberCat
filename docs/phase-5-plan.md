# Phase 5 Execution Plan — Interactive Response

Scope: turn the analyst UI from read-only into a real response tool. Written 2026-04-20.

Read this first, then `PROJECT_STATE.md`, then `docs/api-contract.md` §3 (transitions, notes) + §6 (responses) + §8 (lab assets), then `docs/scenarios/identity-endpoint-chain.md` §"t = ~5 min — Analyst inspects" onward. Those define the contract, the scenario end-state, and the analyst mental model this phase has to deliver.

---

## 0. Why this phase matters (don't skip this)

Phase 4 made the incident *legible*. Phase 5 makes it *actionable*. Every SOAR tool claims automated response; most ship a button that POSTs to a webhook and calls it a product. CyberCat's differentiator is the thing sitting *between* the correlator and the button: a policy engine that classifies every action by blast radius, gates execution on lab scope at propose-time and execute-time, persists reversal state, and surfaces all of that to the analyst before they click.

Phase 5 is where the platform earns the phrase "threat-informed automated incident response." If we ship read-write without the policy engine being honest, we become another shell around `curl`. Hold the line.

### Design principles that make this stand out

1. **Classification has a reason, not just a color.** Every action carries a short human sentence explaining *why* it got its classification (e.g. `reversible: removes a tag, identity remains intact`). Renders next to the badge in the UI. Generated at propose-time from the policy engine, stored on the action so it's stable across UI refactors.
2. **Auto-actions are first-class and visible.** The correlator already proposes `tag_incident` and `elevate_severity`. In Phase 5 those get executed automatically by the executor (classification `auto_safe` only) and shown in the UI with a distinct `proposed_by=system` badge. Analysts see the full loop: detection → correlation → auto-response → human review.
3. **Preview before destructive.** Any action classified `disruptive` or `reversible` shows a confirm step with a summary of *what will happen*, *what entities it affects*, and *how to undo* (if reversible). No single-click destructive operations.
4. **Reversal is a first-class history, not an edit.** Reverting doesn't mutate the prior log — it appends a new `ActionLog` row with `result=ok` and the reversal details. The UI renders this as a thread under the action. Audit stays intact.
5. **Lab scope is checked twice and narrated.** Every action pipes through `lab_assets` at propose-time AND execute-time. Out-of-scope failures return an explicit `out_of_lab_scope` error that names the offending entity. The UI surfaces this as a blocking inline message, not a generic toast.
6. **Transitions are evidence, not just state.** Status changes require a reason for `contained`, `resolved`, and `closed`. The transition panel becomes a narrative column the analyst can read end-to-end after the fact.

These principles are what separate a real incident response platform from a dashboard with buttons. Every section below ties back to one of them.

---

## 1. Pre-work (do before writing any Phase 5 code)

### 1a. Schema audit — done 2026-04-20

Phase 1's migration already provisioned every table Phase 5 needs. Confirmed by grep against `backend/app/db/models.py`:

- `Action` (line 300) — `id`, `incident_id`, `kind`, `classification`, `params` (JSONB), `proposed_by`, `proposed_at`, `status`.
- `ActionLog` (line 334) — `id`, `action_id`, `executed_at`, `executed_by`, `result`, `reason`, `reversal_info` (JSONB).
- `LabAsset` (line 358) — `id`, `kind`, `natural_key`, `registered_at`, `notes`, unique on `(kind, natural_key)`.
- `Note` (line 378) — `id`, `incident_id`, `body`, `author`, `created_at`.
- `IncidentTransition` (exists per Phase 3) — `incident_id`, `from_status`, `to_status`, `at`, `actor`, `reason`.

**No new tables. No new migration for schema.** We do ship a tiny data migration in 1c to preseed lab assets.

### 1b. Add `classification_reason` to actions (optional column, small migration)

The design principle "classification has a reason" requires a stable place to store the sentence. Two options:

- **Option A (chosen):** add a nullable `classification_reason: Text` column to `actions` via a new Alembic migration `0002_action_classification_reason.py`. Backfills null for existing rows; new rows get populated at propose-time.
- Option B: stash it inside `params` as a reserved key. Rejected — mixes policy metadata with action inputs and breaks the params contract.

Migration is a one-column `ADD COLUMN`, safe, instant on an empty lab DB.

### 1c. Preseed `lab_assets` for the scenario

The executor cannot let any action through until lab scope exists. Create `backend/alembic/versions/0003_preseed_lab_assets.py` that inserts:

| kind | natural_key | notes |
|---|---|---|
| `user` | `alice@corp.local` | Lab identity for identity-compromise scenario |
| `host` | `lab-win10-01` | Primary Windows lab endpoint |
| `ip` | `203.0.113.7` | Scripted adversary source IP used by `smoke_test_phase3.sh` |

All three are used by `labs/smoke_test_phase3.sh`. Without them, the whole verification gate fails with `out_of_lab_scope`.

### 1d. Move auto-action creation out of the correlator into a hook

The correlator currently creates the incident + attaches detections + opens the transition. It does *not* create auto-actions today. Phase 5 adds a post-correlation hook `propose_auto_actions(incident, db)` that runs inside the same transaction. Keep the correlator's responsibility narrow: shape the incident. The hook is responsible for actions.

### 1e. Authorship convention

Single-operator, single-tenant per CLAUDE.md §4. Pick `"operator@cybercat.local"` as the `author` / `actor` / `executed_by` value when the request originates from the browser. System-initiated actions use `"system:correlator"`. Document this in `docs/runbook.md`; defer real auth to post-v1.

---

## 2. Decisions locked for Phase 5

| Decision | Choice | Reason |
|---|---|---|
| Policy engine location | `backend/app/response/policy.py` — pure module, no DB access | Pure function in, action classification + reason out. Testable without fixtures. |
| Executor location | `backend/app/response/executor.py` — async, DB-aware | Owns scope check, log append, reversal bookkeeping. |
| Executor registry | Dict keyed on `ActionKind` → `ActionHandler` protocol with `execute()` and optional `revert()` | Add new kinds in one file per kind; registry composes them. |
| Auto-execute gate | Only `classification == auto_safe` runs without analyst click | Keeps the autonomy story honest. `reversible`/`disruptive`/`suggest_only` always require a click. |
| Side effects in v1 | DB-only (tag writes, status writes, log rows). No real quarantines, no external calls. | Lab-safe default per CLAUDE.md §4. Real side effects land when Wazuh bridge arrives (Phase 8). |
| API routes | FastAPI routers `incidents.py` (transitions, notes) + new `responses.py` (actions) + new `lab_assets.py` | Matches `api-contract.md` layout; keeps per-domain routers small. |
| Frontend data strategy | Optimistic UI for notes only. Transitions and actions refetch after POST. | Notes are append-only and cheap to roll back on error. Transitions/actions change enough of the detail payload that a refetch is simpler than merging. |
| Toast system | `frontend/app/components/Toast.tsx` + provider in `layout.tsx` | Needed for action success/failure feedback. Keep tiny — no deps. |
| Confirm modal | `frontend/app/components/ConfirmDialog.tsx` | Gates destructive actions per principle #3. Tailwind + headless `<dialog>` element; no modal library. |
| OpenAPI codegen | Still deferred | Surface grows in Phase 5 but remains small; hand-typed `api.ts` stays manageable. Revisit in Phase 6 if Actions API params shapes proliferate. |

---

## 3. Work plan

Numbered the way it should be built. Backend first, frontend second. Do not skip ahead.

### 3.1 Response policy engine (`backend/app/response/policy.py`)

Pure function: `classify(kind: ActionKind, params: dict, incident: Incident) -> ClassificationDecision`.

Returns:
```python
class ClassificationDecision(BaseModel):
    classification: ActionClassification
    reason: str  # single sentence, <160 chars, renders next to the badge
```

Classification table (v1):

| `ActionKind` | classification | reason template |
|---|---|---|
| `tag_incident` | `auto_safe` | Adds a label to the incident record; no external effect. |
| `elevate_severity` | `auto_safe` | Raises the incident severity; reversible by transition, no external effect. |
| `flag_host_in_lab` | `reversible` | Marks a lab host as "under investigation"; removable via revert. |
| `invalidate_lab_session` | `reversible` | Invalidates a single lab session token; new logins still allowed. |
| `quarantine_host_lab` | `disruptive` | Isolates the lab host from the lab network until manually released. |
| `kill_process_lab` | `disruptive` | Terminates a running process on the lab host. |
| `block_observable` | `reversible` | Adds an IP/hash to the deny list; removable via revert. |
| `request_evidence` | `suggest_only` | Queues an evidence collection task; analyst must approve externally. |

Unit test coverage: one test per `ActionKind`; one test for the unknown-kind path; one test that `reason` never exceeds 160 chars.

### 3.2 Executor (`backend/app/response/executor.py`)

Public surface:

```python
async def propose_action(
    db: AsyncSession,
    incident_id: UUID,
    kind: ActionKind,
    params: dict,
    proposed_by: ActionProposedBy,
) -> Action: ...

async def execute_action(
    db: AsyncSession,
    action_id: UUID,
    executed_by: str,
) -> tuple[Action, ActionLog]: ...

async def revert_action(
    db: AsyncSession,
    action_id: UUID,
    executed_by: str,
) -> tuple[Action, ActionLog]: ...
```

Responsibilities:

- `propose_action`:
  1. Validate `params` shape against the kind's contract (small per-kind schema module).
  2. Call `policy.classify()`.
  3. Call `_check_lab_scope(params)` — raises `OutOfLabScopeError` if any referenced user/host/ip/observable is missing from `lab_assets`.
  4. Insert `Action` row with classification + reason + status=`proposed`.
- `execute_action`:
  1. Load action; 409 if not `proposed`.
  2. Re-run lab scope check (principle #5).
  3. Dispatch to the per-kind handler in the registry; handler returns `(result, reversal_info | None)`.
  4. Append `ActionLog` row.
  5. Flip `Action.status` based on result.
- `revert_action`:
  1. Load action; must be `executed`, must have `reversal_info` on its log, must be classification `reversible`.
  2. Dispatch to the handler's `revert()`.
  3. Append *new* `ActionLog` row (principle #4 — never mutate the prior log).
  4. Flip `Action.status` to `reverted`.

Per-kind handlers live in `backend/app/response/handlers/{kind}.py`. Phase 5 ships:

- `tag_incident.py` — writes a tag to `Incident.tags` (add column if missing, or store in a `tags: list[str]` on the incident — confirm schema before coding; if tags aren't present, store under `Incident.rationale` metadata or introduce a thin migration). Revert removes the tag.
- `elevate_severity.py` — updates `Incident.severity`; stores prior severity in `reversal_info`. Revert restores prior.
- `flag_host_in_lab.py` — writes a flag into `LabAsset.notes` (prepend a `[under-investigation]` marker). Revert strips it.
- The other five kinds ship as `suggest_only` stubs that log a "not implemented in lab" reason and return `result=skipped`. They round out the UI but don't pretend to quarantine anything.

### 3.3 Auto-action hook in correlator

New function `backend/app/correlation/auto_actions.py::propose_auto_actions(incident, db)`:

- Called from the correlator immediately after the incident's transaction commits the entity/event/detection junctions.
- For `IncidentKind.identity_compromise`:
  - Propose `tag_incident` with `{"tag": "identity-compromise-chain"}`.
  - Propose `elevate_severity` with `{"to": "high"}` — already high today, but the action exists so the severity reason is auditable.
- Immediately executes any `auto_safe` proposal via `executor.execute_action(..., executed_by="system:correlator")`.
- Never executes `reversible`/`disruptive` — those wait for analyst click.

Wire into `backend/app/correlation/rules/identity_compromise.py` at the end of the rule body.

### 3.4 Transitions API (`POST /v1/incidents/{id}/transitions`)

Already specced in `api-contract.md` §3. Implementation in `backend/app/api/routers/incidents.py`:

- Load incident (404 `incident_not_found` if missing).
- Validate `to_status` against the allowed-transitions table (api-contract §3 — encode as a dict-of-sets).
- 409 `invalid_transition` with a human reason on violation.
- Insert `IncidentTransition` row with `actor="operator@cybercat.local"`, `reason` from body, `from_status` = current, `at` = now.
- Update `incidents.status`, `incidents.updated_at`; set `closed_at` if `to_status == closed`.
- Return `TransitionOut`.

Server-side rule: `reason` required (min 1 char after trim) when `to_status in {contained, resolved, closed}`. 422 `reason_required` if absent. Supports principle #6.

### 3.5 Notes API (`POST /v1/incidents/{id}/notes`)

Insert `Note` row with `author="operator@cybercat.local"`, `body` (1–4000 chars, trimmed), `created_at=now`. Return `NoteRef`. 404 on unknown incident. 422 `body_too_short` / `body_too_long`.

### 3.6 Responses API (`backend/app/api/routers/responses.py`)

Four endpoints per `api-contract.md` §6:

- `GET /v1/responses` — filter by incident_id/status/classification, cursor pagination, returns `ActionSummary` list. Read-only list view is useful for a future "all actions" dashboard; not strictly required for the scenario demo, but small enough to ship.
- `POST /v1/responses` — analyst-initiated propose. Body: `{incident_id, kind, params}`. Returns `ActionSummary`. 422 on shape/scope errors.
- `POST /v1/responses/{id}/execute` — calls `executor.execute_action`. Returns `{action, log}`.
- `POST /v1/responses/{id}/revert` — calls `executor.revert_action`. Returns `{action, log}`.

Error envelope matches `api-contract.md` §Conventions (problem-style JSON with stable `code`).

### 3.7 Lab assets API (`backend/app/api/routers/lab_assets.py`)

`GET /v1/lab/assets` list, `POST /v1/lab/assets` register, `DELETE /v1/lab/assets/{id}` deregister. Per `api-contract.md` §8. Thin CRUD; needed so the analyst can add a new lab host without editing a migration. No UI in Phase 5 — expose via `/docs` only. UI lands in Phase 6.

### 3.8 Frontend: polling refetch hook (`frontend/app/lib/usePolling.ts`)

Add a `refetch` return value that callers can invoke after a POST. Already present per summary — double-check it exists and fire it from every Phase 5 write path. No new dependency.

### 3.9 Frontend: transitions affordance

- In the detail header (`frontend/app/incidents/[id]/page.tsx`), add a `<TransitionMenu>` dropdown next to the `StatusPill`. Options filtered by the allowed-transitions map (hard-coded on the client from the same table as the backend — a comment documents that they must stay in sync).
- Clicking an option opens `ConfirmDialog` showing: current → new, optional reason field (required when destination is `contained`/`resolved`/`closed`).
- On submit: POST, then `refetch()` incident detail; show success toast `"Status updated to {status}"` or error toast.
- New component: `frontend/app/components/TransitionMenu.tsx`.

### 3.10 Frontend: notes composer

- In `NotesPanel`, add a textarea + Post button. Character counter (1/4000). Enter submits if ctrl/cmd-held.
- Optimistic: append a temp `NoteRef` with `id="tmp-…"` and `author="operator@cybercat.local"`; replace with the real response; roll back on error.
- Empty state keeps the existing "No notes yet" copy but adds the composer below.

### 3.11 Frontend: action controls

For each row in `ActionsPanel`:

- Render `ClassificationBadge` + a one-line `classification_reason` underneath (new — requires the backend field from §1b).
- If `status == "proposed"`:
  - `auto_safe` → no button (backend auto-executes). The row should never be seen in state `proposed` for `auto_safe`, but if it is, render a disabled "auto-executing…" chip.
  - `suggest_only` → disabled "Not executable" button with a tooltip explaining `suggest_only`.
  - `reversible` / `disruptive` → "Execute" button. Click opens `ConfirmDialog` with a summary panel: kind, params, classification, reason. For `disruptive` the confirm dialog requires typing the incident ID to unlock the submit button (the only interaction that earns that friction per principle #3).
- If `status == "executed"` and classification `reversible`: "Revert" button → `ConfirmDialog` → POST → refetch.
- If `status in {failed, skipped, reverted}`: no button, just the status + last log reason.

Below each action, render its `ActionLog` thread (newest first) as a small vertical list: `executed_at`, `executed_by`, `result`, `reason`, and a collapsed `reversal_info` JsonBlock if present.

### 3.12 Frontend: "Propose action" affordance (minimal)

Not wiring the full proposal form for every kind. Ship a single "Propose action" button that opens a modal with:

- A `<select>` of `ActionKind` values.
- A small kind-specific form generated from a map in `frontend/app/lib/actionForms.ts`. For the three kinds Phase 5 actually executes (`tag_incident`, `elevate_severity`, `flag_host_in_lab`), show real fields. For the rest, show a disabled option with a "coming soon" note.
- Submit → POST → refetch. On `out_of_lab_scope` error, show the offending entity inline (principle #5).

### 3.13 Frontend: toasts + confirm dialog primitives

- `Toast.tsx` with a minimal context/provider. Three flavors: success (emerald), error (red), info (sky). Auto-dismiss at 4s for success/info; sticky for errors until click.
- `ConfirmDialog.tsx` wrapping `<dialog>` with backdrop, ESC-to-close, focus trap via `inert` on body. Takes `{title, body, confirmLabel, danger?: boolean, requireTypedConfirmation?: string}`.
- Wire provider into `app/layout.tsx` above `<main>`.

### 3.14 Scenario runner upgrade (`labs/smoke_test_phase5.sh`)

Extends the Phase 3 script. After the incident exists:

- `curl POST /v1/incidents/{id}/transitions new→triaged`.
- `curl POST /v1/incidents/{id}/notes` with a canned body.
- `curl POST /v1/responses` proposing `flag_host_in_lab`.
- `curl POST /v1/responses/{id}/execute`.
- `curl GET /v1/incidents/{id}` and grep for the expected state.

Keep the Phase 3 script intact; Phase 5 script sources it so regressions in earlier phases are caught.

---

## 4. Verification gate (Phase 5 is not "done" until all pass)

Reset DB (`docker compose down -v && docker compose up -d`) before running. Each check exercised manually.

1. `npm run typecheck` clean in `frontend/`. Zero `any` added. Zero `eslint-disable` added without a `TODO(phase-6)` comment.
2. Pytest (backend): new unit tests for `policy.classify()` cover every `ActionKind`. Executor integration test: propose → execute → revert round-trip for `flag_host_in_lab`.
3. Fresh DB: `labs/smoke_test_phase5.sh` runs green end-to-end.
4. Browser flow, with no terminal assistance:
   - Visit `/incidents` → empty.
   - Seed via the scenario: 4× `auth.failed` + 1× `auth.succeeded` for alice.
   - Within 10s the incident appears.
   - Open detail. Confirm Actions panel shows two `executed` system actions (`tag_incident`, `elevate_severity`) with `proposed_by=system` badge, with a classification reason sentence rendered under each badge.
5. Transition flow: click status pill → menu shows `triaged`/`closed` → select `triaged` → modal opens → submit without reason → toast "Status updated" → transitions panel shows new row. Repeat for `triaged → investigating → contained` (last one requires a reason; try submitting without one to confirm the 422 path renders inline).
6. Note flow: add a note "Alice confirmed she did not travel" → optimistic append → within 1s it settles with real `id`. Stop backend, add another note → error toast, temp row rolls back.
7. Action flow (reversible): in the Actions panel, click "Propose action" → select `flag_host_in_lab` → target `lab-win10-01` → submit → row appears as `proposed` `reversible` with reason. Click Execute → confirm dialog → submit → row flips to `executed`, log appended showing `executed_by=operator@cybercat.local`. Click Revert → dialog → submit → `status=reverted`, second log row appended showing reversal details. The original log row is unchanged (principle #4).
8. Action flow (scope rejection): propose `flag_host_in_lab` for `not-a-lab-host` → expect inline `out_of_lab_scope` error naming the offending `host:not-a-lab-host`. No row created. Confirm with a GET that no `Action` exists.
9. Invalid transition: use the OpenAPI docs to POST `closed → investigating` on a closed incident (close it first). 409 `invalid_transition` returned with human message.
10. Disruptive gate: temporarily make `kill_process_lab` a real handler (or force the UI path) and confirm the confirm dialog requires typing the incident ID before Execute is enabled. Revert the temp change before commit.

Only when 1–10 pass, update `PROJECT_STATE.md` to flip Phase 5 to complete. Do not claim partial wins.

---

## 5. Out of scope for Phase 5 (deferred, with the phase they belong to)

| Feature | Deferred to |
|---|---|
| Entity detail page `/entities/{id}` + entity cross-linking in timeline | Phase 6 |
| `GET /v1/entities` search, `GET /v1/detections` filter UI | Phase 6 |
| ATT&CK catalog endpoint + cached local data | Phase 6 |
| Lab assets CRUD UI | Phase 6 |
| Endpoint-compromise correlation growth (process.created joining incident) | Phase 6 |
| OpenAPI → TS codegen | Phase 6 if surface grows; else Phase 7 |
| Auth / login | Post-v1 (per ADR-0001 / CLAUDE.md §4) |
| Real side effects (actual quarantines, real session kills) | Phase 8 (ADR-0004, Wazuh bridge) |
| SSE / WebSocket push | Post-v1 (per `api-contract.md` §11) |

---

## 6. Risks and mitigations

- **Scope is the biggest so far.** Policy + executor + 4 APIs + 3 frontend flows + primitives. If halfway through week one the burn rate looks wrong, split into 5a (backend + transitions/notes UI) and 5b (actions UI + propose modal). Document the split in `PROJECT_STATE.md` before coding further.
- **Executor side effects leak globally.** Auto-action hook runs inside the correlator transaction — if an auto-action handler raises, it rolls back the incident creation. Mitigation: auto-action execution happens *after* the correlator commits. Handlers get their own transaction.
- **Reversal correctness.** `reversal_info` shape must be stable per-kind. Mitigation: define a `ReversalInfo` per-kind pydantic model, serialize to JSONB. Unit test round-trip per kind.
- **Atomicity of propose + auto-execute.** If propose commits but auto-execute crashes, we leave a `proposed` `auto_safe` action sitting. Mitigation: a startup sweep on backend boot runs pending `auto_safe` actions to completion. Keeps the invariant that `auto_safe` never stays `proposed`.
- **Optimistic notes race.** Two tabs adding notes at once can show ordering drift. Acceptable for v1 — notes are append-only and any drift resolves on the next poll (5s max).
- **Color / focus accessibility on modals.** Confirm dialog must trap focus and close on ESC. Verify with keyboard-only traversal.
- **Turbopack HMR + new files.** Adding components sometimes requires a dev server restart on Windows + Docker. Document in runbook.

---

## 7. Handoff note for Phase 6

Things Phase 6 will want from us:

- Every entity rendered in the detail page should already be a clickable chip routing to `/entities/{id}`. Phase 5 ships the chip *as a link* with `href="/entities/..."` even though the target page 404s — so Phase 6 is a page add, not a chip refactor.
- The ATT&CK panel should be structured to accept `AttackEntry` objects (name + description) from a future catalog endpoint. Today we render `id` only; leave the hooks in place so names can slot in without a re-layout.
- The propose-action modal's form registry (`frontend/app/lib/actionForms.ts`) is the obvious place to add the remaining kinds. Keep its shape stable so Phase 6 just fills in new entries.
- If `GET /v1/responses` turns out to be useful in this phase, a top-level `/actions` page in Phase 6 is nearly free.

Leaving these hooks in place makes Phase 6 an additive patch rather than a rewrite.
