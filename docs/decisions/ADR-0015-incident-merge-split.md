# ADR-0015 — Incident Merge & Split (Phase 20 §C)

**Date:** 2026-05-05
**Status:** Accepted
**Deciders:** Oziel (owner)
**Extends:** ADR-0001 (project scope), ADR-0008 (realtime streaming)

---

## Context

Through Phase 19, an incident's identity was effectively immutable. Once
a correlator opened an incident, the only mutations available to the
analyst were status transitions, notes, and proposing/executing actions.
Two real analyst affordances were missing:

1. **Merge** — when the platform's correlators have produced two
   incidents that an analyst recognizes as the *same investigation*
   (e.g., `identity_compromise` for alice + `endpoint_compromise` on
   alice's host opened ~30 minutes apart), they need a way to fold one
   into the other so triage doesn't fragment.
2. **Split** — when an incident has accumulated evidence that an analyst
   recognizes belongs to a *different* investigation (e.g., a noisy
   workstation correlated with a real attacker pivot), they need a way
   to lift that evidence off into a new incident.

Both are standard SOC affordances. CyberCat is a "tested SOC platform"
post-Phase-20 (per the Phase 20 plan framing); shipping these closes
the gap between "polished detection demo" and "platform analysts can
actually drive end-to-end."

---

## Decisions

### 1. Schema: nullable `parent_incident_id` FK + new `'merged'` enum value

**Chosen:** Self-referential nullable FK on `incidents.parent_incident_id`
(`ON DELETE SET NULL`) plus a new `'merged'` value in the
`incident_status` enum. The `IncidentTransition` table is the durable
audit log for both merge and split events.

**Why nullable FK over a junction table.** An incident can be merged into
exactly one parent at a time. If a merge is later reversed (out of scope
in Phase 20 — explicit Phase 24+ feature), the source becomes a brand-new
incident; the original `IncidentTransition` row preserves "this used to
be merged into X" history. A junction table (`incident_merges (source,
target, ...)`) would only matter for n-way merges, which we explicitly
exclude (see "Out of scope" below).

**Why a new enum value over a separate `merged_at` timestamp.** Status
is the analyst's primary filter. `WHERE status != 'merged'` lets the
default incident list hide already-folded incidents without joining the
transition table. A timestamp would force every list view to filter on
a column that's NULL for the common case — slower in Postgres, more
intrusive in the SQLAlchemy model definitions.

### 2. Merge mechanics: bulk-move junctions + Postgres advisory lock

**Chosen:** `merge_incidents()` (`backend/app/correlation/merge.py`)
acquires a transaction-scoped Postgres advisory lock keyed on the
deterministic `(min(src,tgt), max(src,tgt))` pair, then `SELECT ... FOR
UPDATE` on both rows, then bulk-moves event/entity/detection/ATT&CK
junction rows from source → target with `ON CONFLICT DO NOTHING`. Source
gets `status='merged'` and `parent_incident_id=target.id`; target keeps
its kind and gets aggregate updates (`severity = max`, `confidence = avg`).
Two `IncidentTransition` rows audit the operation. SSE bus publishes
`incident.merged` for both IDs.

**Why advisory lock over row lock alone.** `SELECT FOR UPDATE` would
prevent concurrent mutation of a single row, but a merge involves *two*
rows. Two operators clicking "merge A → B" and "merge B → A"
simultaneously would each lock different rows in different orders →
deadlock. The advisory lock keyed on the canonicalized pair serializes
those operations cleanly: both transactions compute the same key, the
second blocks until the first commits or rolls back.

**Why bulk-move junctions and not soft-delete-and-recreate.** Soft delete
loses the original event/detection IDs that downstream tools (logs,
external SIEM exports, the SSE stream) already reference. Moving the
junction rows preserves all evidence IDs.

### 3. Split mechanics: cut, don't copy

**Chosen:** `split_incident()` (`backend/app/correlation/split.py`)
*moves* selected events and entities from the source incident to a new
child incident — `DELETE FROM incident_events ... WHERE event_id IN ...`
on the source side, then `INSERT` on the child side. Detections that
fired on moved events are *copied* to the child (not removed from the
source) because computing "is this detection still represented on the
source?" reliably is non-trivial in the general case. Source aggregates
get recomputed against remaining detections.

**Why split children do NOT set `parent_incident_id`.** Splitting is
"this evidence belongs to a different incident now," not the inverse of
merge. A split child is a fresh investigation with its own
trajectory — pointing it at a parent would suggest a structural
relationship that may no longer hold. The audit link is the
`IncidentTransition` row referencing both IDs by reason text. This
keeps the parent FK semantically clean: `parent_incident_id IS NOT NULL`
unambiguously means "this incident was merged into the referenced one."

### 4. API: two routes, analyst+ role gated

**Chosen:** `POST /v1/incidents/{id}/merge-into` (body `{target_id,
reason}`) and `POST /v1/incidents/{id}/split` (body `{event_ids,
entity_ids, reason}`). Both gated by `Depends(require_analyst)`. Errors
map to 422 (validation: self-merge, empty selection, events-not-in-source),
404 (missing source/target), 409 (already-merged source, closed/merged
target). Both return the resulting incident's full `IncidentDetail`.

### 5. Downgrade is intentionally asymmetric

Migration 0009's `upgrade()` is symmetric (column + FK + index + enum
value). `downgrade()` drops the FK and column cleanly but **does not
remove** `'merged'` from the enum. Postgres < 17 has no native
`ALTER TYPE ... DROP VALUE`; even on 17+ it's blocked while any row
still references the value. Operationally we only ever downgrade fresh
DBs, so this asymmetry is acceptable and documented in the migration
docstring.

---

## Alternatives rejected

- **(a) Junction table `incident_merges (source, target, merged_at, ...)`.**
  Only useful for n-way merges. We're explicit about staying 2-way (see
  Out of scope). The nullable FK is simpler and answers the same questions
  for the 2-way case.
- **(b) Soft-delete-and-recreate the source on merge.** Loses event/
  detection ID continuity for downstream consumers (SSE clients, log
  exports). Forces re-keying in every place that references incident IDs.
- **(c) Event-sourced rebuild.** Persist merge/split as immutable events,
  rebuild incident state by replaying. Massive complexity for one
  feature; would force every incident-touching code path to consult an
  event log. Out of scale for the project.
- **(d) Auto-merge based on entity overlap.** Phase 24+, blocked by the
  no-ML rule (CLAUDE.md §4) for any non-trivial similarity threshold.

---

## Consequences

**Wins:**
- Analysts can fold duplicate-investigation incidents in one click
  instead of working two parallel triages.
- Analysts can lift misfiled evidence off into a new incident without
  rewriting state by hand.
- The audit log answers "where did this evidence come from?" reliably
  via `IncidentTransition.reason` text.

**Limits we accept:**
- **Migration 0009 downgrade can't remove `'merged'` from the enum.**
  Documented; only matters for fresh-DB downgrade, which is the only
  downgrade we run anyway.
- **Operator-only.** No auto-merge / auto-split. Auto-merge is Phase 24+
  and gated on the no-ML rule.
- **Merge is one-way.** Once merged, the source incident is no longer
  visible in the default list. Reversing a merge requires manual analyst
  work (open the merged source, copy needed evidence to a new incident,
  add a note linking the originals). Phase 24+ may add an "unmerge"
  affordance.
- **Split confidence stays as-is on source.** Recomputing confidence
  against remaining detections is mechanically possible but the formula
  is not well-defined when detections have heterogeneous confidence
  hints. Documented in `split.py`. Analyst can manually adjust if needed.
- **Cross-`kind` merges absorb without re-kinding.** When merging an
  `endpoint_compromise` into an `identity_compromise`, the target keeps
  `kind='identity_compromise'`. The IncidentTransition row records that
  endpoint evidence was absorbed. Re-kinding would require a "what kind
  is this incident now?" decision the platform isn't equipped to make.
- **Split-of-merged-incident is rejected** at the API layer (422
  `source_closed`). A merged source is a closed chapter; touching its
  evidence breaks the merge audit.

---

## Out of scope

- N-way merges (only 2-way merge — fold A into B; do that twice in
  succession to fold A and B into C).
- Auto-merge / auto-split (Phase 24+).
- Frontend "drill mode" / training-state UI affordances around
  merge/split (Phase 24+).
- Reverse-merge / "unmerge" UX (Phase 24+; the data model supports it
  via the `parent_incident_id` FK, but no UI).
- Cross-kind smart re-kinding on merge (the IncidentTransition row
  records the cross-kind absorption; the kind itself doesn't change).

---

## References

- `docs/phase-20-plan.md` §C (the Phase 20 plan that drove this ADR)
- `backend/alembic/versions/0009_incident_merge_split.py` (the migration)
- `backend/app/correlation/merge.py` + `backend/app/correlation/split.py`
- `backend/app/api/routers/incidents.py` (the two new routes)
- `backend/tests/integration/test_incident_merge.py` +
  `test_incident_split.py` (the §C6 test suite)
