# Phase 15 — Recommended Response Actions

## Context

CyberCat already has a fully wired response layer (8 handlers, classified by safety, all human-in-the-loop). When an analyst opens an incident today, they see the story (timeline, detections, entities, ATT&CK) but the response side is a blank `Propose action` button — they have to *think* about which of the 8 action kinds is appropriate, *figure out* the right target (which host? which IP?), and *type or pick* the params themselves. That's friction. New analysts won't know that "T1110 brute force from a known IP → block_observable on that IP" is the obvious move.

This phase adds a **Recommended Response Actions** panel on the incident detail page that surfaces 2–4 ranked, pre-filled action suggestions for each incident. Each suggestion has a "Use this" button that opens the existing `ProposeActionModal` pre-populated with the correct kind + params + target entity. The analyst still clicks Execute — nothing fires automatically — but the *decision* is reduced from "what should I do?" to "yes, do that." This is purely additive UX: detection, correlation, handlers, audit, gating, classification, revertability — all unchanged.

**Outcome:** Every incident becomes self-guiding. Demos visibly improve (every incident has a "fight back" panel pre-filled). Closes the loop on the "explainable response" half of the product story to match the explainable-detection half that's already done.

---

## Design overview

### Recommendation model

A `RecommendedAction` is a candidate response with everything needed to one-click prefill the modal:

```
{
  kind:                  ActionKind          # e.g. "block_observable"
  params:                dict[str, Any]      # handler-specific, ready to submit
  rationale:             str                 # 1-sentence "why" (mirrors incident.rationale style)
  classification:        ActionClassification # for UI badge color
  classification_reason: str                 # from policy.classify(kind).reason
  priority:              int                 # 1 = highest; sort key
  target_summary:        str                 # short label like "203.0.113.42" for the panel chip
}
```

### Two-level mapping (static, code-resident, reviewable in PRs)

**Level 1 — incident kind → candidate set.** Each `IncidentKind` has a base list of action kinds that are reasonable to suggest:

| IncidentKind | Base candidates |
|---|---|
| `identity_compromise` | `request_evidence`, `block_observable` (on source_ip), `invalidate_lab_session`, `flag_host_in_lab` |
| `endpoint_compromise` | `request_evidence`, `quarantine_host_lab`, `flag_host_in_lab`, `block_observable` (any source_ip) |
| `identity_endpoint_chain` | `request_evidence`, `quarantine_host_lab`, `invalidate_lab_session`, `block_observable`, `flag_host_in_lab` |
| `unknown` | `request_evidence` only |

**Level 2 — ATT&CK technique → priority boost.** For every technique present on the incident, raise the priority of the most relevant action:

| Technique prefix | Boosts |
|---|---|
| `T1110` (Brute Force) | `block_observable` on source_ip ↑↑ |
| `T1078` (Valid Accounts) | `invalidate_lab_session` ↑↑ |
| `T1059` (Command & Scripting Interpreter) | `quarantine_host_lab` ↑ |
| `T1021` (Lateral Movement) | `quarantine_host_lab` ↑↑ |
| `T1071` / `T1571` (C2 / Non-standard port) | `block_observable` on C2 IP ↑↑ |
| (none / unknown) | no boost; base order applies |

Match by `technique.startswith(prefix)` so subtechniques (`T1110.003`) inherit. Use `incident.attack[].technique` from the existing `IncidentDetail` schema.

### Entity resolution (filling params)

Walk `incident.entities` once to bucket by role:

| Role | Used for |
|---|---|
| `user` | `invalidate_lab_session.user` |
| `host` | `quarantine_host_lab.host`, `kill_process_lab.host`, `flag_host_in_lab.host`, `invalidate_lab_session.host`, `request_evidence.target_host` |
| `source_ip` | `block_observable.value` (with `kind="ip"`) |
| `observable` | `block_observable.value` (kind from entity attrs) |

If the entity needed for a candidate isn't present, **drop the candidate**. Don't suggest `block_observable` if no IP was identified; don't suggest `quarantine_host_lab` if no host. The recommender produces *valid, executable* suggestions or none.

### Decisions locked in (call these out so user can redirect)

1. **Top-N = 4.** Show up to 4 ranked recommendations. More clutters; fewer feels thin on chains.
2. **Filter already-executed actions.** If an action with the same `(kind, params)` was already executed on this incident and not reverted, drop it from recommendations. Reverted actions stay eligible. Implementation: walk `incident.actions` (already on `IncidentDetail`), skip candidates whose `(kind, params)` matches a non-reverted executed action.
3. **Exclude `tag_incident` and `elevate_severity`.** These are auto-safe admin actions, not defensive responses. They confuse the "fight back" framing. Available via the regular Propose flow if needed.
4. **`kill_process_lab` is excluded by default.** The handler requires `pid` + `process_name`, and the incident model doesn't reliably carry a live PID (no `process` entity is created today). Re-add later if/when a process entity is wired into incidents.
5. **Empty-state is rendered, not hidden.** Panel always shows; if 0 recs, render "No recommended actions for this incident." The panel signals the system *considered* and concluded — not that it's broken.
6. **Separate endpoint, not embedded in `IncidentDetail`.** Easier to test in isolation, matches the existing pattern (responses are separate), keeps `IncidentDetail` schema stable. Frontend fetches alongside the incident.
7. **Phase number: 15.** Phase 14 (auth) is closed and verified. This is a new product feature, not a sub-phase. Aligns with `PROJECT_STATE.md`'s "next phase" position.

---

## Sub-phase 15.1 — Backend recommender + endpoint

**Goal:** A pure function that takes an incident (model or detail) and returns a sorted list of `RecommendedAction`s, plus a thin REST endpoint that exposes it. Tested in isolation.

### Files

**New — `backend/app/response/recommendations.py`** (~150 lines)
- `@dataclass(frozen=True) RecommendedAction` — exact shape above
- `_BASE_CANDIDATES: dict[IncidentKind, list[ActionKind]]` — Level 1 table from design
- `_TECHNIQUE_BOOSTS: list[tuple[str, ActionKind, int]]` — Level 2 boosts (prefix, action, score)
- `recommend_for_incident(incident: Incident, *, max_results: int = 4) -> list[RecommendedAction]`
  - Fetch related: `incident.entities`, `incident.attack`, `incident.actions` (use joinedload via the caller; the function takes a fully loaded Incident)
  - Bucket entities by role (user, host, source_ip, observable)
  - For each base candidate kind: try to construct `params` from buckets; skip if unfillable
  - For each technique on the incident: apply matching boosts
  - Subtract `(kind, params)` already-executed-and-not-reverted from `incident.actions`
  - Sort by priority desc, take top N
  - For each, call `classify(kind)` from `app.response.policy` to fill classification + reason
  - Build human rationale per candidate using a small per-action templater (see "Rationale strings" below)

**New — `backend/app/api/schemas/incidents.py` (modify)**
- Add `RecommendedActionOut(BaseModel)` mirroring the dataclass above (uuid + datetime fields not relevant; this is computed, not persisted)

**Modify — `backend/app/api/routers/incidents.py`**
- Add `GET /v1/incidents/{incident_id}/recommended-actions`
  - `Depends(require_user)` — read endpoint, all roles
  - Load incident with `selectinload(Incident.entities, .actions)` and the attack join (existing `_load_incident_detail` style — reuse if it exists, otherwise inline the loads)
  - Call `recommend_for_incident(incident)`
  - Return `list[RecommendedActionOut]`
  - 404 if incident not found

### Rationale strings (small templater)

Each candidate gets a 1-sentence rationale. Templated, not free-form, so they stay consistent and reviewable. Examples:

| Action | Rationale template |
|---|---|
| `block_observable` (T1110 boost) | `"Brute-force pattern observed from {ip} — adding to deny list cuts off the attacker's source."` |
| `block_observable` (T1071 boost) | `"Outbound C2 traffic detected to {ip} — denying it severs the channel."` |
| `block_observable` (no boost) | `"Source IP {ip} is implicated in this incident; deny-listing prevents further activity."` |
| `quarantine_host_lab` (T1021/T1059 boost) | `"Suspicious execution observed on {host} — isolating it prevents further spread."` |
| `quarantine_host_lab` (no boost) | `"Containment of {host} is reasonable while investigation proceeds."` |
| `invalidate_lab_session` | `"Session for {user} on {host} should be killed if the credentials may have been compromised."` |
| `flag_host_in_lab` | `"Mark {host} as under investigation to surface it in dashboards."` |
| `request_evidence` | `"Collect a {evidence_kind} from {host} to support the investigation."` (always-on, low priority) |

Keep at module top in a `_RATIONALES` dict.

### Tests

**New — `backend/tests/unit/test_recommendations.py`** (~10 tests)
- Empty entities → empty recommendations (except `request_evidence` if no host either → also empty)
- `identity_compromise` with `user`+`source_ip` entities → top rec is `block_observable` on the IP, includes `invalidate_lab_session`
- `identity_endpoint_chain` with `user`+`host`+`source_ip` and T1110+T1078+T1059 → 4 recs with `block_observable` and `quarantine_host_lab` ranked above `request_evidence`
- `endpoint_compromise` with only `host` → no `block_observable` (no IP), `quarantine` and `request_evidence` present
- Already-executed `block_observable` on 1.2.3.4 → not re-recommended; reverted same → still recommended
- T1110.003 (subtechnique) → matches T1110 boost
- `tag_incident` and `elevate_severity` never appear
- `unknown` incident kind → only `request_evidence` if host present, else empty

**New — `backend/tests/integration/test_recommendations_endpoint.py`** (~4 tests)
- Anonymous → 401 (`AUTH_REQUIRED=true` test path) using existing `_anon_client` pattern from `test_auth_gating.py`
- `read_only` user → 200 (read endpoint)
- Unknown incident id → 404
- Real incident from a fixture → response shape matches `list[RecommendedActionOut]`, sorted, classification fields populated

### Verification (15.1)

- `cd backend && pytest tests/unit/test_recommendations.py tests/integration/test_recommendations_endpoint.py` → green
- `pytest` full suite → still 156+ green (no regression)
- `curl http://localhost:8000/v1/incidents/{chain-id}/recommended-actions` after firing `credential_theft_chain` → returns 4 entries with expected ranking

---

## Sub-phase 15.2 — Frontend plumbing (modal prefill + API client)

**Goal:** Make `ProposeActionModal` accept an optional `prefill` prop, and add the typed API client method. No visible UI change yet. Verifies cleanly with `tsc --noEmit`.

### Files

**Modify — `frontend/app/lib/api.ts`**
- Add types:
  ```ts
  export interface RecommendedAction {
    kind: ActionKind
    params: Record<string, unknown>
    rationale: string
    classification: ActionClassification
    classification_reason: string
    priority: number
    target_summary: string
  }
  ```
- Add fetcher: `getRecommendedActions(incidentId: string): Promise<RecommendedAction[]>` — wraps `request<RecommendedAction[]>(\`/v1/incidents/${incidentId}/recommended-actions\`)`

**Modify — `frontend/app/incidents/[id]/ProposeActionModal.tsx`**
- Extend props:
  ```ts
  interface ProposeActionModalProps {
    open: boolean
    incidentId: string
    onClose: () => void
    onProposed: () => void
    prefill?: { kind: ActionKind; form: Record<string, string> }  // NEW
  }
  ```
- In the existing `useEffect` that resets state when `open` flips true, **also apply `prefill`** if provided: `setKind(prefill.kind)` and `setForm(prefill.form)`. If `open` flips back to false, clear it on next open (no leakage between sessions).
- The `params` builder (`formDef.buildParams(form)`) already converts the form dict to the right submit shape, so prefill values must use the **string-form keys** the modal already uses (e.g., `host`, `pid`, `value`, `kind` for observable). Backend's `recommend_for_incident` must produce params shaped to these same keys — document this contract in a comment in `recommendations.py`.

### Verification (15.2)

- `cd frontend && npm run typecheck` → 0 errors
- Manually open the modal via the existing "Propose action" button (no prefill passed) → behaves identically to today
- Stub a prefill in DevTools (or temporary harness): modal opens with the action kind selected and form fields populated

---

## Sub-phase 15.3 — Frontend RecommendedActionsPanel + page integration

**Goal:** Render the new panel on the incident detail page; lift modal state from `ActionsPanel` to `page.tsx` so both panels can drive it.

### Files

**Refactor — `frontend/app/incidents/[id]/ActionsPanel.tsx`**
- Remove the `proposeOpen` state and the `<ProposeActionModal />` render
- Replace internal `setProposeOpen(true)` button with a call to a new `onPropose: () => void` callback prop
- New props: `onPropose: () => void` (in addition to existing)

**Modify — `frontend/app/incidents/[id]/page.tsx`**
- Add page-level state: `const [proposeOpen, setProposeOpen] = useState(false)` and `const [prefill, setPrefill] = useState<{kind, form} | undefined>()`
- Add helper `openPropose = (p?: typeof prefill) => { setPrefill(p); setProposeOpen(true) }`
- Pass `onPropose={() => openPropose()}` to `ActionsPanel` (no prefill — manual mode)
- Pass `onUseRecommendation={(rec) => openPropose({kind: rec.kind, form: rec.params as Record<string,string>})}` to the new `RecommendedActionsPanel`
- Render single `<ProposeActionModal open={proposeOpen} incidentId={incident.id} onClose={() => setProposeOpen(false)} onProposed={() => { setProposeOpen(false); refetch() }} prefill={prefill} />` at the page level (outside the grid, near the bottom alongside the page-level dialog area)
- **Insert `<RecommendedActionsPanel incidentId={incident.id} onUseRecommendation={...} />` directly above `<ActionsPanel ... />`** in the right column of the two-column grid

**New — `frontend/app/incidents/[id]/RecommendedActionsPanel.tsx`** (~120 lines)
- Props: `{ incidentId: string; onUseRecommendation: (rec: RecommendedAction) => void }`
- On mount + when `incidentId` changes: fetch `getRecommendedActions(incidentId)`. Re-fetch when SSE topics `actions` or `incidents` fire for this incident (use the existing `useStream` hook with topic filter, similar to the page's incident fetch — or simpler: a small `useEffect` that listens to a passed-in `refreshKey` from the page). **Simplest: take a `refreshKey: number` prop driven by the page's existing `useStream`-triggered re-renders, refetch on change.**
- Render structure:
  - `<Panel title="Recommended Response" count={recs.length} headerAction={<HelpHint />}>`
  - For each rec, a card-like row with:
    - Top row: `<ActionClassificationBadge classification={rec.classification} />` + bold action label (humanized: "Block 203.0.113.42" using `target_summary`) + small priority pill
    - Rationale text (the `rec.rationale` string) below
    - `target_summary` rendered as `<EntityChip>` when the param is an entity-like value (otherwise just text)
    - Right-aligned button: `<button onClick={() => onUseRecommendation(rec)} disabled={!canMutate}>Use this</button>` with the standard `title={!canMutate ? "Read-only role" : undefined}` pattern
- Empty state: `<p className="text-sm text-zinc-500">No recommended actions for this incident.</p>`
- Loading state: skeleton or `Loading recommendations…`
- Error state: small inline message `Could not load recommendations.` with a retry button

### Reuse (do not re-create)

- `Panel` from `frontend/app/components/Panel.tsx`
- `EntityChip` from `frontend/app/components/EntityChip.tsx`
- `ActionClassificationBadge` from `frontend/app/components/ActionClassificationBadge.tsx`
- `useCanMutate` from `frontend/app/lib/SessionContext.tsx`
- `request()` / `getRecommendedActions()` from `frontend/app/lib/api.ts`

### Verification (15.3)

- `cd frontend && npm run typecheck` → 0 errors
- Stack restart, browser open `http://localhost:3000/incidents/{credential_theft_chain chain-id}` → panel renders above ActionsPanel with 3–4 recs
- Click "Use this" on the top rec (block_observable on 203.0.113.42) → modal opens with `block_observable` selected and `value=203.0.113.42`, `kind=ip` prefilled → click Propose → action proposed with correct params
- Click Execute → action runs → page refetches → that recommendation drops out of the panel (executed filter)
- Click Revert → that recommendation reappears
- Switch to a `read_only` role user (via `python -m app.cli set-role`) → "Use this" buttons render disabled with the standard tooltip
- 0-recommendation case: open an incident with no entities → panel shows empty-state message, page doesn't crash

---

## Sub-phase 15.4 — Smoke test + project state update

### Files

**New — `labs/smoke_test_phase15.sh`** (~50 lines, mirrors phase13 style)
- Truncate DB and flush Redis
- Fire `credential_theft_chain` scenario
- Find the `identity_endpoint_chain` incident id
- `curl GET /v1/incidents/{id}/recommended-actions` → assert:
  - status 200
  - body is a JSON array of length ≥ 3
  - first entry has `kind == "block_observable"` and `params.value == "203.0.113.42"`
  - all entries have `classification`, `rationale`, `priority` fields populated
  - none have kind in `{tag_incident, elevate_severity, kill_process_lab}`
- Propose + execute the top recommendation via existing `/v1/responses` endpoint
- Re-fetch recommendations → assert `block_observable` for 203.0.113.42 is gone
- Revert the action → re-fetch → assert it's back
- Print `PASS`/`FAIL` per check, exit non-zero on any fail
- Honour `AUTH_REQUIRED=true` mode by reading a token from env (mirror `smoke_test_phase11.sh` pattern)

**Modify — `PROJECT_STATE.md`**
- Header: Last updated → 2026-04-XX, Phase 15 verified
- Status summary: add Phase 15 line
- New "Phase 15 — Recommended Response Actions" section above Phase 14.4 (newest-first ordering already used)
- Verification log: tests count, smoke 9/9, browser-verified date

**Optional — `docs/decisions/ADR-0010-recommended-actions.md`** (lightweight ADR)
- Decision: static two-level mapping over ML
- Why: explainability, reviewability, no training data
- Tradeoff acknowledged: no auto-learning; revisit when rule pack grows

### Verification (15.4)

- `bash labs/smoke_test_phase15.sh` → all checks pass with `AUTH_REQUIRED=false`
- Re-run with `AUTH_REQUIRED=true` and a Bearer token → all checks pass
- Full pytest suite → still green
- `npm run typecheck` → 0 errors
- Manual UI walk: fire scenario, open incident, click through Use this → Execute → verify revert path → recommendations re-rank live (SSE)

---

## Critical files reference (consolidated)

**Backend — modify:**
- `backend/app/api/schemas/incidents.py` — add `RecommendedActionOut`
- `backend/app/api/routers/incidents.py` — add endpoint
- `backend/app/response/policy.py` — read-only (call `classify()`)

**Backend — create:**
- `backend/app/response/recommendations.py` — recommender engine
- `backend/tests/unit/test_recommendations.py`
- `backend/tests/integration/test_recommendations_endpoint.py`

**Frontend — modify:**
- `frontend/app/lib/api.ts` — add `getRecommendedActions` + types
- `frontend/app/incidents/[id]/ProposeActionModal.tsx` — add `prefill` prop
- `frontend/app/incidents/[id]/ActionsPanel.tsx` — drop modal ownership, accept `onPropose`
- `frontend/app/incidents/[id]/page.tsx` — lift modal state, render new panel

**Frontend — create:**
- `frontend/app/incidents/[id]/RecommendedActionsPanel.tsx`

**Smoke + docs:**
- `labs/smoke_test_phase15.sh`
- `PROJECT_STATE.md`
- (optional) `docs/decisions/ADR-0010-recommended-actions.md`

---

## End-to-end verification (after all four sub-phases)

1. `docker compose up -d` (full stack)
2. `python -m labs.simulator --scenario credential_theft_chain --speed 0.1`
3. Open `http://localhost:3000/incidents/{chain-incident-id}`
4. **Recommended Response** panel appears in the right column, above Actions
5. Top recommendation: "Block 203.0.113.42" (block_observable, `value=203.0.113.42`, `kind=ip`), classification = reversible
6. Click "Use this" → modal opens with everything pre-filled → Propose → Execute → action runs
7. Recommendation drops from the panel (executed filter)
8. Revert from Actions panel → recommendation reappears (live via SSE)
9. Switch to a read_only user → "Use this" disabled with tooltip
10. `pytest` (156 + ~14 new = 170 tests passing)
11. `npm run typecheck` → 0 errors
12. `bash labs/smoke_test_phase15.sh` → all checks pass

---

## Risks / things to flag during implementation

1. **Param-key contract drift.** The recommender produces `params` dicts, the modal's form keys, and the handlers' expected param shapes must all align. Mitigation: write the per-action param keys once at the top of `recommendations.py` as a `_PARAM_KEYS` constant and reference it from both code and tests. If a key changes, the typed test fails.
2. **Action lifting refactor on `ActionsPanel`.** Lifting modal state to the page is small but touches the existing "Propose action" button. Verify the no-prefill path still works exactly as today before building the panel.
3. **SSE refetch coordination.** Panel must refresh when actions change. Cheapest path: drive a `refreshKey` from the existing page-level `useStream`. Don't open a second SSE connection.
4. **Already-executed filter and `block_observable`.** Two `block_observable` actions with different IPs are *different* recommendations — match on `(kind, params.value)` for observables, not just `kind`. Document the equivalence rule in code.
5. **Empty incidents.** Defensive: never crash on incidents with `entities=[]` or `attack=[]`. Return empty list, panel shows empty state.
