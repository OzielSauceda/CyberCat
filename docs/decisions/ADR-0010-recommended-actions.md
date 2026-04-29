# ADR-0010 — Recommended Response Actions Engine (Phase 15)

**Status:** Accepted
**Date:** 2026-04-28
**Deciders:** Oziel (owner)

---

## Context

By the end of Phase 14 the response layer had eight first-class action handlers, all classified by safety, all human-in-the-loop. But the analyst experience on the incident detail page asked too much of the human: when an incident opened, the only response affordance was a generic "Propose action" button that dropped them into an empty modal. They had to:

1. Recognize the incident pattern (e.g. "T1110 brute force from a known IP").
2. Map the pattern to the right action kind (e.g. `block_observable` on the source IP).
3. Type or pick the correct params (the IP value, the kind=ip selector).

That is fine for an experienced operator who already knows the eight kinds. It is friction for anyone newer, and it leaves the "fight back" half of the product story implicit while the "explain the detection" half is already explicit (rationale, attack tags, named entities, kill chain panel).

Phase 15's goal: make every incident self-guiding by surfacing 2–4 ranked, pre-filled action suggestions directly on the detail page. Click "Use this" → modal opens fully populated → analyst still hits Execute. The *decision* is reduced from "what should I do?" to "yes, do that." Detection, correlation, handlers, audit, gating, classification, and revertability all stay unchanged — this is purely additive UX over the existing response surface.

---

## Decisions

### 1. Static two-level mapping (code-resident), not ML

**Chosen:** A small in-code table that maps `IncidentKind` to a list of base candidate action kinds (Level 1), and a list of ATT&CK technique-prefix → action-kind boosts (Level 2). Match Level 2 by `technique.startswith(prefix)` so subtechniques inherit. Sum scores, sort, take top N.

**Rejected alternatives:**
- *ML-trained ranker over historical analyst behavior.* CyberCat has no operator history yet — the data set is the lab seeder and a handful of demo runs. A model trained on that is meaningless. Even with real telemetry, an ML ranker would obscure *why* a recommendation appears, which contradicts CyberCat's explainability contract (`docs/architecture.md §7`). Defer until there's both a non-trivial corpus and a clear win over the rule pack.
- *Per-rule recommendation hints attached to detection rules.* Tempting because detection rules already encode "what fired," but it pushes the recommender's logic into the detection pack and conflates two concerns. A recommendation depends on the *incident's combined* signals, not just the latest detection — incidents grow over time and the right action shifts as more techniques pile on.
- *Free-form LLM call at request time.* Same explainability problem as ML, plus latency, cost, and non-determinism. A static table is sub-millisecond and reviewable in PRs.

The two-level structure mirrors how an analyst actually thinks: *first* "what kind of incident is this?" (sets a default action menu), *then* "which techniques are present?" (raises specific actions to the top). It's the simplest decomposition that captures real prioritization without overengineering.

### 2. Recommend only valid, executable suggestions

**Chosen:** If the entity required by a candidate action isn't present on the incident, drop the candidate. The recommender never returns an action the analyst can't immediately execute.

For example: `block_observable` requires a `source_ip` (or `observable`) entity. On the chain incident — which carries `user` + `host` but not `source_ip` (the chain correlator merges identity + endpoint signals but the source IP lives on the parent identity_compromise incident) — `block_observable` is not recommended. The analyst sees `quarantine_host_lab`, `invalidate_lab_session`, `flag_host_in_lab`, `request_evidence` instead, all built from entities that *are* present.

**Why this matters:** the panel is also a discoverability surface. If we recommended actions that fail with "you didn't pick a host," we'd train analysts to ignore the panel. By emitting only fully-formed candidates, "Use this → Propose → Execute" is a three-click path with no decision-back-loop.

**Accepted trade-off:** the demo incident (`identity_endpoint_chain` from `credential_theft_chain`) does not show "Block 203.0.113.42" in its top recommendation, even though that's arguably the *most* useful action across the whole attack story. The analyst gets it on the parent identity_compromise incident instead. Enriching the chain incident's entities with source_ip is a chain-correlator concern, deferred to a future ADR.

### 3. Already-executed-and-not-reverted actions are filtered out

**Chosen:** Walk `incident.actions`, build a set of `(kind, params)` keys for every action with status `executed` or `partial` (not `reverted`), and drop matching candidates. Reverted actions stay eligible.

**Special case for `block_observable`:** match on `(kind, params.value)` only, not the full params dict. Two `block_observable` actions with different `value`s are *different* recommendations, but two with the same value are the same recommendation regardless of any other param drift (e.g. `kind=ip` vs `kind=domain` — but in practice `(kind, value)` collisions don't happen across blockable kinds).

**Why filter at all:** the panel exists to drive the analyst toward the next decision. Recommending an action they already ran clutters the surface and breaks the "decision is reduced" framing. Reverted actions stay eligible because revert is the analyst saying "that was wrong, I want the option again."

### 4. Excluded action kinds: `tag_incident`, `elevate_severity`, `kill_process_lab`

**Chosen:** Three of the eight action kinds are never recommended:

- `tag_incident` and `elevate_severity` are admin/meta actions, not defensive responses. They confuse the "fight back" framing of the recommended-response panel. Both remain available via the standard Propose flow.
- `kill_process_lab` requires `pid` + `process_name`, neither of which the incident model reliably carries today (no `process` entity gets created during normal ingest). Re-add when a process entity is wired into incidents.

This is a deliberate scope tightening so the panel stays high-signal. Recommending five kinds with clear targets beats recommending eight kinds, three of which require manual followup.

### 5. Separate read-only endpoint, not embedded in `IncidentDetail`

**Chosen:** `GET /v1/incidents/{id}/recommended-actions` returns `list[RecommendedActionOut]`. Computed fresh per request, never persisted.

**Rejected alternatives:**
- *Embed in `IncidentDetail`.* Would couple the recommender's input loads (entities, attack, actions) to the main detail query and grow the response payload. The existing `IncidentDetail` schema is already large; recommendations are an independent concern that the frontend fetches alongside.
- *Persist materialized recommendations.* Adds DB writes on every incident mutation and gives nothing back — recommendations are cheap to recompute and depend on multiple moving inputs (entities, attack tags, action history). Compute-on-read is correct here.

Read endpoint allowed for any authenticated role (`require_user`) — recommendations are a read operation; mutating them isn't a thing.

### 6. Param keys aligned with frontend modal form keys (contract documented in code)

**Chosen:** The recommender's `params` dict uses the same keys as the `ProposeActionModal` form state, so the frontend can pass the dict straight into the modal's `prefill.form` prop with no translation layer.

| Action | Param keys |
|---|---|
| `block_observable` | `kind`, `value` |
| `quarantine_host_lab`, `flag_host_in_lab` | `host` |
| `invalidate_lab_session` | `user`, `host` |
| `request_evidence` | `evidence_kind`, `target_host` |

Documented at the top of `backend/app/response/recommendations.py` so any future drift fails loudly: tests pin the param shapes and the modal's `formDef.buildParams` assumes these keys.

### 7. Modal ownership lifted from `ActionsPanel` to `page.tsx`

**Chosen:** The `ProposeActionModal` is rendered once at the page level. Both `ActionsPanel` (manual-mode, no prefill) and `RecommendedActionsPanel` (prefill from a clicked recommendation) drive it via callbacks (`onPropose`, `onUseRecommendation`). The new `prefill?: { kind, form }` prop on the modal pre-populates state on open and clears on close.

**Why:** two panels needing to open the same modal would otherwise either duplicate modal instances (state divergence, focus bugs) or require routing modal state through props/context. Lifting to the parent is the standard React pattern for "two children, one modal."

---

## Consequences

**Positive:**
- Every incident becomes self-guiding. New analysts (or returning operators after a long gap) get a "fight back" cheat sheet without needing to remember the eight action kinds.
- The "explainable response" half of the product story now matches the explainable-detection half. A recommendation comes with a rationale, a classification badge, and a target chip — analysts can see *why* before they click.
- Static rules are reviewable in PRs. Anyone reading `recommendations.py` can see what gets recommended, in what order, and why.
- Zero behavior change to detection/correlation/handlers/audit. If you turn the panel off, nothing else moves.

**Negative / accepted trade-offs:**
- The rule pack will grow as incidents and techniques diversify. At some point a 50-line table becomes harder to reason about than a small priority engine — revisit when there are >20 entries or >5 techniques per action.
- The chain incident does not show `block_observable` on its top rec because the chain correlator doesn't carry `source_ip`. This is a real demo-narrative gap; the parent incident covers it.
- No auto-learning. If an operator consistently dismisses a particular recommendation, the system never adapts. Acceptable at v1 — the frequency of "Use this" vs "ignore" isn't tracked yet, and a thumbs-down loop would be premature without analyst-history data.

**Future revisits:**
- Carry `source_ip` into `identity_endpoint_chain` incidents (chain-correlator change) so the chain demo's top rec lines up with intuition.
- Track "rec shown / rec used" telemetry per `(IncidentKind, technique-prefix, ActionKind)` triple. After enough data, the static boosts become tunable from real outcomes — and *that* is when an ML or learned ranker becomes worth considering.
- Add a per-action `feedback` button ("not useful here") that writes a row into a future `recommendation_feedback` table. Drives both the telemetry above and a future "snooze this rec on this incident" feature.

---

## Files changed in Phase 15

**Backend:**
- `backend/app/response/recommendations.py` (new) — engine + `RecommendedAction` dataclass + tables + helpers.
- `backend/app/api/schemas/incidents.py` — `RecommendedActionOut` pydantic model.
- `backend/app/api/routers/incidents.py` — `GET /v1/incidents/{id}/recommended-actions` endpoint.
- `backend/tests/unit/test_recommendations.py` (new) — 13 unit tests.
- `backend/tests/integration/test_recommendations_endpoint.py` (new) — 4 integration tests.

**Frontend:**
- `frontend/app/lib/api.ts` — `RecommendedAction` type + `getRecommendedActions(incidentId)` fetcher.
- `frontend/app/incidents/[id]/ProposeActionModal.tsx` — `prefill?: { kind, form }` prop + open-state lifecycle handling.
- `frontend/app/incidents/[id]/ActionsPanel.tsx` — drops local modal ownership; accepts `onPropose` callback.
- `frontend/app/incidents/[id]/page.tsx` — page-level modal state + `RecommendedActionsPanel` integration.
- `frontend/app/incidents/[id]/RecommendedActionsPanel.tsx` (new) — the panel itself.

**Smoke / docs:**
- `labs/smoke_test_phase15.sh` (new) — 21-check end-to-end smoke.
- `docs/phase-15-plan.md` — original plan (kept for history).
- `docs/architecture.md`, `docs/api-contract.md`, `docs/runbook.md` — updated with Phase 15.
