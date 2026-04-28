# API Contract — CyberCat (v1)

The first product API surface. Source of truth for FastAPI routers (Phase 2+) and the generated TypeScript client consumed by the frontend (Phase 5). Schemas are expressed in pydantic-style sketches; the final pydantic models live in `backend/app/api/schemas/` and emit the OpenAPI the frontend reads.

All endpoints are JSON. Auth is implemented as of Phase 14 (ADR-0009). When `AUTH_REQUIRED=true`, every endpoint except `/healthz` and `/readyz` requires either a valid session cookie or a `Authorization: Bearer cct_...` API token. See §10 for the full auth surface. When `AUTH_REQUIRED=false` (the default), all endpoints are open — used for local dev and CI.

Base URL: `http://localhost:8000`

All product endpoints are prefixed with `/v1/` (e.g. `/v1/incidents`, `/v1/events/raw`). Health endpoints (`/healthz`, `/readyz`) are unversioned. The paths in this document omit the prefix for brevity but the implementation includes it.

---

## Conventions

- **IDs:** UUIDs as strings.
- **Timestamps:** RFC 3339 UTC with `Z` suffix, e.g. `"2026-04-19T17:04:32Z"`.
- **Errors:** Problem-style JSON: `{ "error": { "code": "<stable_code>", "message": "<human>", "details": {...} } }`. HTTP status matches the category (400 validation, 404 not found, 409 conflict, 422 rule violation, 500 internal).
- **Pagination:** `?limit=<int, default 50, max 200>&cursor=<opaque>` → response `{items: [...], next_cursor: "..." | null}`.
- **Enums** on the wire match Postgres enum values exactly (lowercase snake_case).

---

## 1. Health

### `GET /healthz`
Liveness only. No DB check.

**Response 200:**
```json
{ "status": "ok", "version": "<git_sha>" }
```

### `GET /readyz`
Readiness. Pings Postgres and Redis.

**Response 200:**
```json
{ "status": "ready", "postgres": "ok", "redis": "ok" }
```

**Response 503:** same shape with failing components marked `"error"`.

---

## 2. Ingest

### `POST /events/raw`
Direct ingest adapter. Used by the seeder, tests, and any non-Wazuh feeder. The Wazuh adapter (Phase 8) does **not** use this endpoint — it calls the normalizer directly inside the process.

**Request:**
```python
class RawEventIn(BaseModel):
    source: Literal["direct", "seeder"]
    kind: str                           # e.g. "auth.failed"
    occurred_at: datetime
    raw: dict                           # original shape
    normalized: dict                    # must satisfy the kind's normalized contract
    dedupe_key: str | None = None
```

**Response 201:**
```python
class RawEventAccepted(BaseModel):
    event_id: UUID
    dedup_hit: bool                     # true if dedupe_key matched existing event; event_id points to the original
    detections_fired: list[UUID]        # detection IDs produced synchronously
    incident_touched: UUID | None       # incident opened or grown, if any
```

**Errors:**
- 400 `invalid_kind` — kind not in the known taxonomy.
- 422 `normalized_shape_mismatch` — `normalized` doesn't match the kind's contract (see `docs/data-model.md` §2).

---

## 3. Incidents

### `GET /incidents`
List incidents with filtering.

**Query params:**
- `status=new,triaged,...` (comma-separated enum values)
- `severity_gte=medium` (inclusive; ordered `info < low < medium < high < critical`)
- `entity_id=<uuid>` (filter to incidents where this entity participates)
- `opened_after=<rfc3339>`
- `limit`, `cursor`

**Response 200:**
```python
class IncidentSummary(BaseModel):
    id: UUID
    title: str
    kind: IncidentKind
    status: IncidentStatus
    severity: Severity
    confidence: Decimal                 # 0.00–1.00
    opened_at: datetime
    updated_at: datetime
    entity_count: int
    detection_count: int
    event_count: int
    # lightweight entity preview for list-view cards
    primary_user: str | None            # natural_key of user entity if any
    primary_host: str | None            # natural_key of host entity if any

class IncidentList(BaseModel):
    items: list[IncidentSummary]
    next_cursor: str | None
```

### `GET /incidents/{id}`
Full incident detail — powers the hero UI view.

**Response 200:**
```python
class EntityRef(BaseModel):
    id: UUID
    kind: EntityKind
    natural_key: str
    attrs: dict                         # kind-specific, see data-model §1
    role_in_incident: str               # from incident_entities.role

class DetectionRef(BaseModel):
    id: UUID
    rule_id: str
    rule_source: Literal["sigma", "py"]
    rule_version: str
    severity_hint: Severity
    confidence_hint: Decimal
    attack_tags: list[str]
    matched_fields: dict
    event_id: UUID
    created_at: datetime

class TimelineEvent(BaseModel):
    id: UUID
    occurred_at: datetime
    kind: str
    source: Literal["wazuh", "direct", "seeder"]
    normalized: dict
    role_in_incident: Literal["trigger", "supporting", "context"]
    entity_ids: list[UUID]              # entities linked to this event (via event_entities)

class AttackRef(BaseModel):
    tactic: str                         # e.g. "TA0006"
    technique: str                      # e.g. "T1110"
    subtechnique: str | None
    source: Literal["rule_derived", "correlator_inferred"]

class ActionSummary(BaseModel):
    id: UUID
    kind: ActionKind
    classification: Literal["auto_safe", "suggest_only", "reversible", "disruptive"]
    classification_reason: str | None    # human-readable sentence explaining the classification
    status: Literal["proposed", "executed", "failed", "skipped", "reverted", "partial"]
    params: dict
    proposed_by: Literal["system", "analyst"]
    proposed_at: datetime
    last_log: ActionLogSummary | None

class ActionLogSummary(BaseModel):
    executed_at: datetime
    executed_by: str
    result: Literal["ok", "fail", "skipped", "partial"]   # "partial" = DB state committed, AR dispatch failed
    reason: str | None
    reversal_info: dict | None           # for AR-dispatched actions includes ar_dispatch_status, ar_command, ar_agent_id, manager error (if any)

class TransitionRef(BaseModel):
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    actor: str
    reason: str | None
    at: datetime

class IncidentDetail(BaseModel):
    id: UUID
    title: str
    kind: IncidentKind
    status: IncidentStatus
    severity: Severity
    confidence: Decimal
    rationale: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    correlator_rule: str
    correlator_version: str

    entities: list[EntityRef]
    detections: list[DetectionRef]
    timeline: list[TimelineEvent]       # sorted occurred_at ASC
    attack: list[AttackRef]
    actions: list[ActionSummary]
    transitions: list[TransitionRef]
    notes: list[NoteRef]
```

**Errors:**
- 404 `incident_not_found`.

### `POST /incidents/{id}/transitions`
Change status. Validates allowed transitions server-side.

**Request:**
```python
class TransitionIn(BaseModel):
    to_status: IncidentStatus
    reason: str | None = None
```

**Response 201:**
```python
class TransitionOut(BaseModel):
    incident_id: UUID
    from_status: IncidentStatus
    to_status: IncidentStatus
    at: datetime
```

**Errors:**
- 409 `invalid_transition` — e.g. `closed → investigating`.
- 404 `incident_not_found`.

**Allowed transitions (v1):**
```
new          → triaged, closed
triaged      → investigating, closed
investigating→ contained, resolved, closed
contained    → resolved, investigating (reopen), closed
resolved     → closed, investigating (reopen)
closed       → (terminal)
```

### `POST /incidents/{id}/notes`
Analyst annotation.

**Request:**
```python
class NoteIn(BaseModel):
    body: str                           # required, 1–4000 chars
```

**Response 201:**
```python
class NoteRef(BaseModel):
    id: UUID
    body: str
    author: str
    created_at: datetime
```

---

## 4. Entities

### `GET /entities/{id}`
Entity detail.

**Response 200:**
```python
class EntityTimelineEvent(BaseModel):
    id: UUID
    occurred_at: datetime
    kind: str
    normalized: dict

class EntityIncidentSummary(BaseModel):
    id: UUID
    title: str
    kind: IncidentKind
    status: IncidentStatus
    severity: Severity
    confidence: Decimal
    opened_at: datetime
    updated_at: datetime

class EntityDetail(BaseModel):
    id: UUID
    kind: EntityKind
    natural_key: str
    attrs: dict
    first_seen: datetime
    last_seen: datetime
    recent_events: list[EntityTimelineEvent]   # last 50, sorted occurred_at DESC
    related_incidents: list[EntityIncidentSummary]
```

### `GET /entities?kind=&natural_key=`
Lookup by natural key (used by frontend cross-links and seeder sanity checks).

---

## 5. Detections

### `GET /detections`
Filter detections.

**Query params:**
- `incident_id=<uuid>`
- `rule_id=<str>`
- `rule_source=sigma|py`
- `since=<rfc3339>`
- `limit`, `cursor`

**Response 200:**
```python
class DetectionItem(BaseModel):
    id: UUID
    rule_id: str
    rule_source: Literal["sigma", "py"]
    rule_version: str
    severity_hint: Severity
    confidence_hint: Decimal
    attack_tags: list[str]
    matched_fields: dict
    event_id: UUID
    incident_id: UUID | None     # resolved via IncidentDetection join; null if unlinked
    created_at: datetime

class DetectionList(BaseModel):
    items: list[DetectionItem]
    next_cursor: str | None
```

---

## 6. Responses (actions)

### `GET /responses`
Filter action records.

**Query params:**
- `incident_id=<uuid>` (typical)
- `status=proposed,executed,...`
- `classification=auto_safe,...`
- `limit`, `cursor`

**Response 200:**
```python
class ResponseList(BaseModel):
    items: list[ActionSummary]
    next_cursor: str | None
```

### `POST /responses`
Propose a new action (analyst-initiated). System-initiated proposals are created by the correlator directly, not via this endpoint.

**Request:**
```python
class ActionProposeIn(BaseModel):
    incident_id: UUID
    kind: ActionKind
    params: dict                        # validated against kind's contract (data-model §8)
```

**Response 201:**
```python
class ActionProposed(BaseModel):
    action: ActionSummary
```

**Errors:**
- 422 `params_shape_mismatch` — params don't satisfy the kind's contract.
- 422 `out_of_lab_scope` — referenced entity not in `lab_assets`. Returned at propose time *and* re-checked at execute time.

### `POST /responses/{id}/execute`
Execute a proposed action. No body.

**Response 200:**
```python
class ActionExecuted(BaseModel):
    action: ActionSummary               # refreshed, status=executed|failed|skipped
    log: ActionLogSummary
```

**Errors:**
- 404 `action_not_found`.
- 409 `action_not_proposed` — already executed/failed/skipped/reverted.
- 422 `out_of_lab_scope` — entity check failed at execute time.

### `POST /responses/{id}/revert`
Revert a previously executed reversible action. `reversal_info` on the originating log must be present.

**Response 200:** same shape as execute.

**Errors:**
- 409 `not_reversible` — action classification wasn't `reversible` or no `reversal_info` recorded.

---

## 7. ATT&CK

### `GET /attack/catalog`
Returns the local ATT&CK reference data (tactic/technique/subtechnique names + descriptions). Frontend uses this to label tags without hitting MITRE at render time.

**Response 200:**
```python
class AttackEntry(BaseModel):
    id: str                             # "TA0001" | "T1078" | "T1078.002"
    name: str
    url: str                            # MITRE URL
    kind: Literal["tactic", "technique", "subtechnique"]
    parent: str | None                  # technique for subtechniques; tactic for techniques (primary)

class AttackCatalog(BaseModel):
    version: str                        # ATT&CK version we're pinned to
    entries: list[AttackEntry]
```

---

## 8. Lab assets

### `GET /lab/assets`
List registered lab assets (executor scope). Returns `list[LabAssetOut]` — not paginated (bounded set).

**Query params:**
- `kind=user|host|ip|observable` (optional filter)

### `POST /lab/assets`
Register a new asset.

**Request:**
```python
class LabAssetIn(BaseModel):
    kind: Literal["user", "host", "ip", "observable"]
    natural_key: str
    notes: str | None = None
```

**Response 201:**
```python
class LabAssetOut(BaseModel):
    id: UUID
    kind: str
    natural_key: str
    registered_at: datetime
    notes: str | None
```

### `DELETE /lab/assets/{id}`
Remove from scope. Idempotent. Does not touch existing executed actions — this only affects future executor checks.

---

## 8b. Evidence requests (Phase 9A)

### `GET /evidence-requests?incident_id=<uuid>`
List evidence requests for an incident. Auto-proposed ones appear with `proposed_by=system`.

```python
class EvidenceRequestOut(BaseModel):
    id: UUID
    incident_id: UUID
    kind: Literal["process_list", "triage_log", "file_snapshot", "network_dump"]
    status: Literal["open", "collected", "dismissed"]
    target_host: str | None              # natural_key
    target_user: str | None              # natural_key
    requested_at: datetime
    resolved_at: datetime | None
    payload_url: str | None
    notes: str | None
```

### `POST /evidence-requests/{id}/collect`
Mark as collected. Optional `payload_url` + `notes` in the body.

### `POST /evidence-requests/{id}/dismiss`
Mark as dismissed. Optional `notes` in the body.

---

## 8c. Blocked observables (Phase 9A)

### `GET /blocked-observables?active=true`
List currently-blocked observables. Entries are created by the `block_observable` response action (reversible); setting `active=false` (via action revert) stops the `blocked_observable` detector from firing on that value.

```python
class BlockedObservableOut(BaseModel):
    id: UUID
    kind: Literal["ip", "domain", "hash"]
    value: str
    active: bool
    blocked_at: datetime
    blocked_by_action_id: UUID
    incident_id: UUID                    # originating incident (audit trail)
```

---

## 8d. Wazuh bridge status (Phase 8)

### `GET /wazuh/status`
Health of the Wazuh indexer poller. Unauthenticated.

```python
class WazuhStatusOut(BaseModel):
    enabled: bool                        # WAZUH_BRIDGE_ENABLED flag
    reachable: bool                      # last poll attempt result
    last_success_at: datetime | None
    last_error: str | None
    events_ingested_total: int
    has_cursor: bool                     # True once search_after is populated
```

Used by the `WazuhBridgeBadge` in the frontend top-nav.

---

## 9. Shared enums

```python
class EntityKind(str, Enum):
    user = "user"
    host = "host"
    ip = "ip"
    process = "process"
    file = "file"
    observable = "observable"

class IncidentKind(str, Enum):
    identity_compromise = "identity_compromise"
    endpoint_compromise = "endpoint_compromise"
    identity_endpoint_chain = "identity_endpoint_chain"
    unknown = "unknown"

class IncidentStatus(str, Enum):
    new = "new"
    triaged = "triaged"
    investigating = "investigating"
    contained = "contained"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"               # reserved; v1 uses investigating after close-reopen

class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class ActionKind(str, Enum):
    tag_incident = "tag_incident"
    elevate_severity = "elevate_severity"
    flag_host_in_lab = "flag_host_in_lab"
    quarantine_host_lab = "quarantine_host_lab"
    invalidate_lab_session = "invalidate_lab_session"
    block_observable = "block_observable"
    kill_process_lab = "kill_process_lab"
    request_evidence = "request_evidence"
```

---

## 10. Auth surface (Phase 14)

Controlled by `AUTH_REQUIRED` env var (default `false`).

### `POST /auth/login`
Email + password sign-in. Sets an HMAC-signed session cookie (`cybercat_session`, 8h TTL).

**Request:** `{ "email": "...", "password": "..." }`  
**Response 200:** `{ "id": UUID, "email": str, "role": "admin"|"analyst"|"read_only" }`  
**Errors:** 401 `invalid_credentials`.

### `POST /auth/logout`
Clears the session cookie.

### `GET /auth/me`
Returns the current user from the session cookie or Bearer token. Used by the frontend `SessionContext` on mount.

**Response 200:** `{ "id": UUID, "email": str, "role": str }` or `{ "authenticated": false }` when `AUTH_REQUIRED=false`.

### `GET /auth/config`
Returns feature flags for the frontend: `{ "auth_required": bool, "oidc_enabled": bool }`. Always unauthenticated — used before the session is established.

### `GET /auth/oidc/login`
Redirects to the configured OIDC provider's authorization endpoint. Sets a short-lived signed state cookie.  
**Returns:** HTTP 302 to provider, or HTTP 501 if OIDC is not configured.

### `GET /auth/oidc/callback`
Exchanges the authorization code for an ID token, validates the JWT signature + nonce (authlib), JIT-provisions the user if new (role=`read_only`), sets a session cookie, redirects to `/`.

### Gating model

| Verb | Route pattern | Required role |
|------|--------------|---------------|
| `POST` | `/v1/events/raw` | `analyst` |
| `POST/DELETE` | `/v1/responses/*`, `/v1/incidents/*/transitions`, `/v1/incidents/*/notes`, `/v1/evidence-requests/*/collect`, `/v1/evidence-requests/*/dismiss`, `/v1/lab/assets` | `analyst` |
| `GET` | all `/v1/*` endpoints, `/v1/stream` | any authenticated user |
| `GET` | `/healthz`, `/readyz`, `/auth/config` | none (always public) |

`analyst` = `analyst` or `admin` role. `read_only` users can read everything but all mutation controls are disabled in the frontend.

---

## 11. Scenario coverage check

Cross-reference with `docs/scenarios/identity-endpoint-chain.md`:

- Seeder posts 9 events → `POST /events/raw` ×9. ✓
- Incident appears in list → `GET /incidents?status=new`. ✓
- Analyst opens detail → `GET /incidents/{id}` returns timeline, entities, detections, ATT&CK, rationale, actions, transitions. ✓
- Analyst transitions `new → triaged → investigating → contained` → 3 × `POST /incidents/{id}/transitions`. ✓
- Analyst executes `flag_host_in_lab` → `POST /responses/{id}/execute`. ✓
- Auto-tag actions appear in detail response as `executed` with `proposed_by=system`. ✓
- ATT&CK labels render from `GET /attack/catalog`. ✓
- Lab scope enforcement → 422 on `POST /responses/{id}/execute` for out-of-scope target. ✓

No endpoint gaps for v1.

---

## 12. What's explicitly out of v1 API

- ~~WebSocket / SSE push.~~ **Done — Phase 13.** `GET /v1/stream` is live; frontend uses `useStream` with topic filters and a 60s polling fallback.
- ~~Auth endpoints.~~ **Done — Phase 14.** See §10.
- Bulk operations (no `POST /incidents:bulk_close` etc.).
- Full-text search across incidents/events. Filtering is enum/entity-based only.
- Export endpoints (PDF report, STIX bundle, etc.).
- Rule management API (enable/disable Sigma rules at runtime). Rules are file-configured in v1.
- SAML. Intentionally omitted — see ADR-0009.
