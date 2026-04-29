# Phase 2 Execution Plan — Canonical Schema + Normalization

Scope: turn the `POST /v1/events/raw` skeleton into a real ingest pipeline; land the full initial schema; build the normalizer and entity extractor that the rest of the product depends on.

> **Retrospective note.** Reconstructed for the docs archive. Phases 1–3 predate the per-phase plan format; this document captures the scope, decisions, and verification gate the work actually shipped against.

---

## 0. Why this phase matters

Detection and correlation only make sense on top of a clean canonical model. If raw Wazuh alerts and direct-API events are wrangled into different shapes, every downstream rule has to know about both — and that's how detection engines end up unreviewable. Phase 2 enforces the rule that *only* the normalizer touches raw vendor shapes; everything past the normalizer reads a single internal event/entity model.

The canonical model is also the explainability contract. Every incident has to answer: "which events contributed, with which entities in which roles." That answer is unworkable unless events and entities have stable shapes and the junction between them is recorded at ingest time, not retrofitted later.

Design principles that hold for the rest of the project:
1. **Postgres owns truth.** The canonical event, every entity, and the junction between them are written to Postgres synchronously on the ingest path. If the DB write fails, the ingest fails. No "we'll persist it later."
2. **`raw` and `normalized` live side by side.** The raw vendor payload is preserved in JSONB so future detectors and audits can reread it without re-fetching. The normalized shape is what every downstream component reads.
3. **Idempotent entity upsert.** The same user / host / IP appearing in 100 events produces one entity row. PostgreSQL `ON CONFLICT DO UPDATE` on `(kind, natural_key)` is the contract.
4. **Validation at the door.** Each event kind has a required-field registry; missing fields → 422 with a structured error. We never persist a half-shaped event.
5. **One ingestion path, two adapters.** The Wazuh poller (Phase 8) and the direct API will both call the same `pipeline.ingest_event()` function. Decouple adapters from logic now so Phase 8 is small.

---

## 1. Pre-work

### 1a. Confirm Phase 1 baseline

- `docker compose up -d` brings the stack up.
- `POST /v1/events/raw` returns the Phase 1 skeleton 202.
- Alembic version table exists, currently at `0000_init`.

If any of these fail, fix Phase 1 before continuing.

### 1b. Settle the canonical event kinds

The canonical kinds for v1 (ADR-0001 scope: identity + endpoint compromise):

- `auth.failed`
- `auth.succeeded`
- `process.created`
- `session.started`
- `network.connection`

Each has a per-kind required-field set on the `normalized` payload. Locked at the start of the phase so the registry doesn't drift while detectors are being written in Phase 3.

### 1c. Settle the entity kinds

- `user`, `host`, `ip`, `process`, `file`, `observable`

Natural-key shape, per kind:
- `user` — email or `domain\user`; canonicalized lowercase.
- `host` — hostname; lowercase.
- `ip` — string form of v4 or v6; rejected if not parseable.
- `process` — `image|pid` composite; treated as ephemeral.
- `file` — sha256 hex if available, else absolute path.
- `observable` — `kind:value` (e.g. `domain:evil.example`).

---

## 2. Decisions locked for Phase 2

| Decision | Choice | Reason |
|---|---|---|
| Schema migration | Single `0001_initial_schema.py` | The whole Phase 2 + Phase 3 schema lands at once; no point shipping half. |
| Event id | `uuid.UUID` server-generated | Stable, sortable enough via `occurred_at`; no client-supplied IDs. |
| Time fields | `TIMESTAMP WITH TIME ZONE`, always UTC | Avoid timezone bugs forever. |
| `raw` and `normalized` | `JSONB` columns on `events` | Audits and re-decode paths get the original bytes; detectors read normalized. |
| Entity uniqueness | `UNIQUE(kind, natural_key)` | The upsert key. Cited everywhere. |
| Pipeline orchestration | Pure async function `pipeline.ingest_event(...)` | Adapter-agnostic; easy to unit-test. |
| Error envelope | `{error: {code, message, details}}` per `api-contract.md` Conventions | Same shape for 422 / 404 / 409 / 500. |
| Validation library | pydantic at the API boundary; per-kind dataclass schemas inside the normalizer | Boundary-only pydantic keeps the hot path cheap. |

---

## 3. Work plan

### 3.1 Models (`backend/app/db/models.py`)

- `Event` — id, source (`seeder` / `wazuh` / `direct`), kind, occurred_at, ingested_at, raw JSONB, normalized JSONB.
- `Entity` — id, kind, natural_key, attrs JSONB, first_seen, last_seen. `UNIQUE(kind, natural_key)`.
- `EventEntity` — junction. `(event_id, entity_id, role)` composite PK; role is a string (e.g. `actor`, `target_host`, `source_ip`, `target_user`, `process`, `parent_process`).
- The incident-related tables (`incidents`, `detections`, `incident_*` junctions, `notes`, `incident_transitions`) ship in this same migration but are read-empty until Phase 3 starts writing them. Pre-shipping the schema avoids a Phase 3 migration and a Phase 3 re-deploy.

Migration file: `backend/alembic/versions/0001_initial_schema.py`.

### 3.2 Enums (`backend/app/enums.py`)

- `EventKind` — the 5 canonical kinds.
- `EntityKind` — the 6 entity kinds.
- `IncidentKind`, `IncidentStatus`, `Severity`, `RoleInIncident`, `IncidentEntityRole`, `AttackSource` — declared now so Phase 3 doesn't have to migrate the enum types. SQLAlchemy creates the underlying Postgres enum types in migration `0001`.

### 3.3 Normalizer (`backend/app/ingest/normalizer.py`)

- `_REQUIRED_FIELDS: dict[EventKind, set[str]]` — for each kind, the set of fields that must be present on `normalized`.
  - `auth.failed` / `auth.succeeded` → `{user, source_ip, auth_type}`
  - `process.created` → `{user, host, image, pid}`
  - `session.started` → `{user, host, session_id}`
  - `network.connection` → `{host, dest_ip, dest_port}`
- `validate(kind, normalized) -> None` — raises `ValidationError` with structured details on missing fields.
- The normalizer never mutates the raw payload. It only validates. Mapping from vendor shape → normalized shape lives in adapters (Phase 8 for Wazuh; the direct API expects the caller to send a pre-shaped `normalized` body).

### 3.4 Entity extractor (`backend/app/ingest/entity_extractor.py`)

- `extract_entities(kind, normalized) -> list[EntityRef]` — pure function; for each event kind, returns the entities and their roles per `IncidentEntityRole`.
- `upsert_entities(db, refs) -> dict[EntityRef, uuid.UUID]` — `ON CONFLICT (kind, natural_key) DO UPDATE` to bump `last_seen`; returns the mapping back to the caller.
- `link_event_entities(db, event_id, refs_with_ids) -> None` — writes `event_entities` rows.

### 3.5 Pipeline (`backend/app/ingest/pipeline.py`)

- `async def ingest_event(db, payload: RawEventIn) -> IngestResult`
- Steps:
  1. Validate via the normalizer.
  2. Insert `events` row.
  3. Extract entities, upsert, link via `event_entities`.
  4. Return `{event_id, detections_fired: [], incident_touched: None}` — last two are placeholders until Phase 3.
- Single transaction. If any step raises, the whole ingest fails and returns 422 / 500.

### 3.6 Direct API (`backend/app/api/routers/events.py`)

- `POST /v1/events/raw`:
  - Request: `RawEventIn` (pydantic): `source`, `kind`, `occurred_at`, `raw`, `normalized`.
  - Response: `IngestResult` (pydantic): `{event_id, detections_fired, incident_touched}`. 202 on success.
- `GET /v1/events`:
  - Cursor-paginated list ordered by `occurred_at desc`. Filters: `kind`, `since`, `limit`, `cursor`. Stub-shipped here; will get more filters when the frontend lands.

### 3.7 Tests

- `backend/tests/unit/test_normalizer.py` — per-kind required-field validation.
- `backend/tests/unit/test_entity_extractor.py` — entity refs produced by each kind; idempotency under repeated calls.
- `backend/tests/integration/test_ingest_pipeline.py` — round-trip: POST `/v1/events/raw` → assert event row, entity rows, event_entities rows.

### 3.8 Docs

- `docs/data-model.md` — fill in `events`, `entities`, `event_entities` sections with column-by-column descriptions.
- `docs/api-contract.md` — fill in §1 (`POST /v1/events/raw`, `GET /v1/events`).
- `docs/runbook.md` — add a "Seed an event" recipe with a working `curl` example.

---

## 4. Verification gate

1. `alembic upgrade head` from a fresh DB applies `0001_initial_schema` cleanly. `alembic downgrade base` round-trips.
2. `pytest backend/tests/` is green; no skipped tests.
3. `POST /v1/events/raw` with a valid `auth.failed` payload returns 202 with a real `event_id`.
4. The same POST repeated 5× produces 5 event rows but only 2 entity rows (1 user + 1 IP) — `ON CONFLICT` works.
5. `POST /v1/events/raw` with a `process.created` payload missing `pid` returns 422 with the structured error envelope.
6. `GET /v1/events?kind=auth.failed` returns the seeded events in `occurred_at desc` order; cursor pagination produces non-overlapping pages.
7. `psql` confirms `event_entities` has the right `(event_id, entity_id, role)` triples for each seeded event.
8. `docker compose down -v && docker compose up -d` reset round-trips: stack comes up clean; first POST succeeds without manual setup.

---

## 5. Out of scope for Phase 2

| Feature | Deferred to |
|---|---|
| Detection rules / Sigma engine | Phase 3 |
| Correlation engine / incident creation | Phase 3 |
| ATT&CK tagging | Phase 3 |
| Wazuh poller adapter | Phase 8 |
| Frontend list/detail pages | Phase 4 |
| Response actions | Phase 5 |
| Auth | Phase 14 |

---

## 6. Risks and mitigations

- **Schema-too-big migration.** Shipping all incident-related tables in `0001_initial_schema` is intentional but means a longer migration to review. Mitigation: every `op.create_table` block is grouped and commented by feature area; the migration's docstring lists the table set.
- **Time-zone footguns.** Postgres `TIMESTAMP WITHOUT TIME ZONE` reads as wall-clock; we exclusively use `TIMESTAMP WITH TIME ZONE`. The pydantic boundary coerces all inputs to UTC. Documented in `data-model.md`.
- **Entity natural-key normalization drift.** Two ingest paths (direct + Wazuh, Phase 8) must produce the same natural keys for the same logical entity. Mitigation: a single `entity_extractor.py` is the only producer; Phase 8's adapter delegates instead of re-deriving.
- **Validation perf.** Pydantic on the boundary is fine; per-kind dataclass validation inside the normalizer keeps the hot path cheap. Re-examine if ingest throughput becomes a real concern.

---

## 7. Handoff note for Phase 3

Phase 3 will:
- Read events as they're persisted and run detectors against them.
- Write `detections` rows tagged with ATT&CK technique IDs.
- Run correlators that build `incidents` and grow the `incident_*` junctions.
- Have `pipeline.ingest_event()`'s return value start populating `detections_fired` and `incident_touched`.

Phase 2 leaves Phase 3 with: a complete schema, a working pipeline, the canonical model nailed down, and a smoke recipe in the runbook.
