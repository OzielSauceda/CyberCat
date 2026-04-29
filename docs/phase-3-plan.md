# Phase 3 Execution Plan — Detection + Correlation + Incident Model

Scope: turn ingested events into fired detections, and turn fired detections into a single, explainable incident. This is where CyberCat stops being a logging pipe and becomes the product.

> **Retrospective note.** Reconstructed for the docs archive. Phases 1–3 predate the per-phase plan format; this document captures the scope, decisions, and verification gate the work actually shipped against.

---

## 0. Why this phase matters

Phase 1 laid rails. Phase 2 made the canonical model real. Phase 3 is the first phase that produces something an analyst would care about: an incident, with rationale, that ties multiple events together via fired rules with ATT&CK tags. Without Phase 3, the rest of the product has nothing to render, nothing to respond to, and no reason to exist.

This phase also nails two architectural rules that have to hold for everything that comes after:

1. **Postgres owns truth, Redis is ephemeral.** Sliding-window failure counts, dedup keys, and cooldowns live in Redis. Detections, incidents, and the junctions that explain them live in Postgres. If Redis dies, the system recovers; if Postgres dies, real incidents are lost. This boundary is non-negotiable.
2. **Every incident is explainable.** The DB retains *which events* and *which rules* contributed, plus a human-readable rationale string written by the correlator at creation time. No black-box scoring; an analyst (or a reviewer skimming the repo) must be able to look at one incident and answer "why is this one incident, not five?" from the row alone.

The flagship Phase 3 demo is the smoke test: 4× `auth.failed` followed by 1× `auth.succeeded` for the same user from the same new source produces *one* `identity_compromise` incident, severity `high`, with both detections linked, both entities linked with roles, and ATT&CK tags `T1110` (Brute Force) and `T1078` (Valid Accounts).

---

## 1. Pre-work

### 1a. Confirm Phase 2 baseline

- `alembic upgrade head` cleanly applies `0001_initial_schema` from a fresh DB.
- `POST /v1/events/raw` with a valid `auth.failed` payload returns 202 with a real `event_id`.
- The repeated-POST entity de-dup case works (5 events, 2 entities).

If any of these fail, fix Phase 2 before continuing.

### 1b. Settle the rule surface

For Phase 3 we are scoping to **two Python detectors** + **one correlator**. No Sigma engine yet (Sigma lands later), no endpoint correlator (`endpoint_compromise_*` rules ship in a later phase), no auto-actions (they ship with the response phase). The minimum viable detection-to-incident loop:

- Detector `py.auth.failed_burst` — ≥4 `auth.failed` for the same user within 60s → fire one detection per crossing.
- Detector `py.auth.anomalous_source_success` — `auth.succeeded` for a user from a `source_ip` that has had recent failures and no prior successful auth → fire detection.
- Correlator `identity_compromise` — opens a new `Incident(kind=identity_compromise)` on `py.auth.anomalous_source_success`, deduped per `{user}:{hour_bucket}`. Pulls in the burst detection by walking back recent detections for the same user.

### 1c. Settle the rationale style

The rationale string is mandatory on every incident, written by the correlator at creation time. Phase 3 sets the voice that every later correlator should match — short, plain, factual, no hedging, no emoji, no marketing.

Example for the smoke case:
> *"4 failed authentications for alice@corp.local from 203.0.113.7 within 5 minutes, followed by a successful authentication from the same previously-unseen source. Pattern consistent with successful credential guessing or password spraying."*

---

## 2. Decisions locked for Phase 3

| Decision | Choice | Reason |
|---|---|---|
| Detection registry | `@register()` decorator + module-level `DETECTORS` list | Each rule self-registers on import; `run_detectors(event)` iterates. |
| Correlator registry | Same `@register()` pattern | Symmetric with detectors; first-match-wins ordering by registration. |
| Sliding window store | Redis sorted set, ZADD with `occurred_at` epoch as score | Range scans + TTL trimming are cheap; no Postgres hot path. |
| Failure-burst threshold | 4 in 60s | Conservative enough to avoid noise on real ssh brute force; tunable per-rule constant. |
| Incident dedup key | `identity_compromise:{user}:{hour_bucket}` in Redis (SETNX) | Hour buckets keep two attacks an hour apart in separate incidents; tighter than per-day, looser than per-minute. |
| Severity / confidence | `high` / `0.80` hardcoded for v1 of this rule | A scoring model lives in a later phase; constants now keep the demo predictable. |
| ATT&CK tagging | `Detection.attack_tags` JSONB list of technique IDs | The catalog table itself ships in a later phase; Phase 3 emits the tag IDs and the incident copies them into `incident_attack` rows with `source=rule_derived`. |
| Junction growth | `extend_incident()` helper using `ON CONFLICT DO NOTHING` | Re-running the pipeline on a duplicate event must be idempotent. |
| Pipeline integration | Detection + correlation run *inside* `pipeline.ingest_event()`'s transaction | One commit per ingest; no half-built incidents under partial failure. |

---

## 3. Work plan

### 3.1 Detection engine (`backend/app/detection/`)

- `engine.py` — `@register()` decorator, `DETECTORS` list, `async def run_detectors(db, event) -> list[Detection]` that calls each registered rule and persists fired detections.
- `rules/auth_failed_burst.py` — uses Redis sorted set `auth.failed:{user}` keyed by user; trims entries older than 60s; if cardinality ≥4, fires `py.auth.failed_burst`. Returns the list of source events to attach to the detection.
- `rules/auth_anomalous_source_success.py` — on `auth.succeeded`, queries Redis for failures from the same user+source_ip in the last 10 min; queries Postgres for prior `auth.succeeded` from this user from the same source; fires when failures present + no prior success from source.
- Each detector returns a `DetectionResult` containing the rule_id, severity_hint, confidence_hint, ATT&CK tag IDs, the matched event(s), and a `matched_fields` dict suitable for the eventual `JsonBlock` rendering on the frontend.

### 3.2 Correlation engine (`backend/app/correlation/`)

- `engine.py` — `@register()` decorator, `CORRELATORS` list, `async def run_correlators(db, event, fired) -> uuid.UUID | None` that returns the touched incident id (creating one if needed).
- `rules/identity_compromise.py` — fires on `py.auth.anomalous_source_success`; computes the dedup key; SETNX in Redis; on first-fire, creates the incident with the rationale; on subsequent fire within the window, calls `extend_incident()` to add the new detection + events + entities.
- `extend.py` — `extend_incident(db, incident_id, detection, events, entities)` writes junction rows with `ON CONFLICT DO NOTHING`. Updates `incidents.updated_at` and recomputes `confidence` if the rule supplies a delta.

### 3.3 Pipeline integration (`backend/app/ingest/pipeline.py`)

- After persisting the event + entities (Phase 2 work), call `run_detectors(db, event)` then `run_correlators(db, event, fired)` within the same transaction.
- `IngestResult` becomes `{event_id, detections_fired: list[uuid.UUID], incident_touched: uuid.UUID | None}`.
- If a detector or correlator raises, the whole ingest rolls back and the API returns 500 with the structured envelope. We never persist the event but skip the rules — that asymmetry would corrupt the explainability contract.

### 3.4 ATT&CK tag plumbing

- `Detection.attack_tags` JSONB column (already in `0001_initial_schema`) gets populated by each detector with technique IDs.
- The correlator copies the tags into `incident_attack` rows with `source=rule_derived` and the contributing `detection_id` pointer.
- A real ATT&CK *catalog* (with tactic, technique, subtechnique names) lands in a later phase. Phase 3 only emits the IDs.

### 3.5 Tests

- `backend/tests/unit/test_auth_failed_burst.py` — fire on 4th, do not fire on 3rd, do not fire 5 minutes later (window expiry).
- `backend/tests/unit/test_auth_anomalous_source_success.py` — fires when failures present + no prior success; does not fire when source has prior success; does not fire when no failures.
- `backend/tests/unit/test_identity_compromise_correlator.py` — opens incident on first fire; extends incident on second fire within hour bucket; opens new incident on second fire in next hour bucket; rationale string contains user, source_ip, failure count.
- `backend/tests/integration/test_ingest_to_incident.py` — full pipeline: 4× `auth.failed` + 1× `auth.succeeded` → assert one incident with severity=high, two detections linked, two entities linked with roles, two ATT&CK rows.

### 3.6 Smoke test

- `labs/smoke_test_phase3.sh` — replays the canonical scenario via `curl`. Outputs:
  - 1st–3rd `auth.failed`: `detections_fired: []`.
  - 4th `auth.failed`: `detections_fired: [<burst-detection-id>]`.
  - `auth.succeeded`: `detections_fired: [<anomalous-source-id>]`, `incident_touched: <incident-id>`.
  - `GET /v1/incidents` lists one item with severity=high, kind=identity_compromise.
- This script becomes the canonical "the loop works" proof for every later phase that touches detection or correlation.

### 3.7 Docs

- `docs/data-model.md` — fill in `detections`, `incidents`, `incident_events`, `incident_detections`, `incident_entities`, `incident_attack`, `incident_transitions` sections.
- `docs/api-contract.md` — `GET /v1/incidents` (list, filters), `GET /v1/incidents/{id}` (detail) — read-only stubs Phase 4 will consume.
- `docs/detection.md` — first draft: how detectors register, the Redis key conventions, the cooldown and dedup rules, the rationale style guide.
- `docs/runbook.md` — add the Phase 3 smoke recipe.

---

## 4. Verification gate

1. `pytest backend/tests/` is green; the integration test above is included.
2. `bash labs/smoke_test_phase3.sh` against a fresh DB produces the expected output at every step (4th failure fires burst; success fires anomalous-source; one incident exists at the end).
3. `GET /v1/incidents` returns 1 item with severity=high, kind=identity_compromise, title containing the user identifier.
4. `GET /v1/incidents/{id}` returns: rationale present, `entities` includes alice (role=user) and 203.0.113.7 (role=source_ip), `detections` includes both fired rules, `timeline` lists all 5 events with `role_in_incident`, `attack` includes T1110 and T1078 with `source=rule_derived`.
5. Repeat the smoke test immediately. The second run does **not** create a second incident (hour-bucket dedup); junction tables grow by `ON CONFLICT DO NOTHING`.
6. Wait an hour (or fast-forward Redis TTL in a test fixture). The third run *does* create a second incident.
7. `psql` audit: `incident_events`, `incident_detections`, `incident_entities`, `incident_attack` all populated; row counts match what the API returned.
8. Kill Redis (`docker compose stop redis`) mid-test → the next ingest fails clean (500 with structured envelope), no half-written incident in Postgres. Restart Redis → ingest resumes.

Only when 1–8 pass, flip Phase 3 to complete in `PROJECT_STATE.md` and move to Phase 4.

---

## 5. Out of scope for Phase 3

| Feature | Deferred to |
|---|---|
| Sigma parser / compiler / pack | Later phase |
| Endpoint correlator (`endpoint_compromise_*`) | Later phase |
| `process.created` detector (suspicious child) | Later phase |
| Auto-proposed actions (`auto_actions.py`) | Phase 5 |
| ATT&CK catalog table + `/v1/attack/catalog` endpoint | Later phase |
| Frontend incidents list / detail | Phase 4 |
| Response action handlers | Phase 5 |
| Wazuh ingestion path | Phase 8 |
| Auth / login | Phase 14 |

---

## 6. Risks and mitigations

- **Redis as detection state means a Redis flush erases short-term context.** Mitigation: documented in `docs/detection.md`; the smoke test resets Redis between runs to make this explicit.
- **First-match-wins correlator ordering can mask a more specific rule.** Mitigation: only one correlator ships in Phase 3; revisit ordering when the second one lands.
- **Hour-bucket dedup splits a real attack across the bucket boundary.** Acknowledged tradeoff for v1; better than coalescing a week of attacks into one incident. Revisit when an analyst flags it.
- **Detector + correlator both inside the ingest transaction means a slow rule blocks ingest.** Mitigation: every detector has a hard 250ms budget; if any detector exceeds it, log a structured warning and surface in the smoke test. Async background detection is a later phase if it becomes necessary.
- **Confidence and severity are constants, not computed.** Acknowledged; the model is too small to score honestly at this stage. The `confidence` column is a Decimal so the day a real model lands, no migration is needed.

---

## 7. Handoff note for Phase 4

Phase 4 (frontend) will consume:
- `GET /v1/incidents` — list with filters; cursor pagination.
- `GET /v1/incidents/{id}` — detail with all junctions populated.
- `Incident.rationale` — rendered as a prominent block.
- `Detection.matched_fields` — surfaced inline in the detections panel; designed to be readable as JSON.
- `incident_attack` rows — rendered as ATT&CK chips with the `source` badge already in place (`rule_derived` here; `correlator_inferred` will exist when later correlators land).

Phase 3 leaves Phase 4 with: a real incident in the DB, a stable detail-endpoint shape, a working smoke recipe, and a rationale style that the frontend's "Why this is one incident" panel can lean on without rewriting.
