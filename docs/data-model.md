# Data Model — CyberCat

Canonical Postgres schema for the product-owned tables. Source of truth for Phase 1 migrations. Pair with `docs/scenarios/identity-endpoint-chain.md` — every column must serve the scenario, and every scenario moment must be expressible in these columns.

Conventions:
- `UUID` primary keys for top-level objects (entities, events, detections, incidents, actions, lab_assets, notes). `BIGSERIAL` for high-volume append-only logs (`incident_transitions`, `action_logs`).
- All timestamps `TIMESTAMPTZ`, stored UTC.
- Enums implemented as Postgres `ENUM` types (not free-text). Listed as `enum(...)` below.
- JSONB used only where the contract is defined in this doc. No "flexible bag" columns.

---

## 1. `entities`

The canonical record for a thing we reason about: a user, host, IP, process, file, or observable.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | generated server-side |
| `kind` | enum(`user`,`host`,`ip`,`process`,`file`,`observable`) | NOT NULL |
| `natural_key` | TEXT | NOT NULL. Canonical string per kind (see below) |
| `attrs` | JSONB | NOT NULL default `'{}'`. Kind-specific metadata; schema per kind below |
| `first_seen` | TIMESTAMPTZ | NOT NULL |
| `last_seen` | TIMESTAMPTZ | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL default `now()` |

**Unique:** `(kind, natural_key)`.
**Indexes:** `(kind, last_seen DESC)`, GIN on `attrs`.

**`natural_key` format by kind:**
- `user`: lowercase principal, e.g. `alice@corp.local`
- `host`: lowercase hostname, e.g. `lab-win10-01`
- `ip`: dotted-quad or IPv6 canonical, e.g. `203.0.113.7`
- `process`: `{host_natural_key}/{pid}/{started_at_epoch}` (pid alone is not unique across hosts or time)
- `file`: `{host_natural_key}:{absolute_path}` or `sha256:<hex>` when content-addressed
- `observable`: `{scheme}:{value}`, e.g. `domain:attacker.example`, `hash:sha256:<hex>`

**`attrs` JSONB contract per kind:**
- `user`: `{display_name?, upn?, mail?, lab_flagged?: bool}`
- `host`: `{os?, os_version?, lab_flagged?: bool, quarantined?: bool}`
- `ip`: `{asn?, country?, tags?: [str]}`
- `process`: `{name?, cmdline?, parent_pid?, image_path?}`
- `file`: `{path?, size?, sha256?}`
- `observable`: `{scheme, value, blocked?: bool, tags?: [str]}`

---

## 2. `events`

Every normalized event. Raw shape preserved in `raw` for explainability; product logic consumes `normalized` + `event_entities`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `occurred_at` | TIMESTAMPTZ | NOT NULL. When the event happened at the source |
| `received_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `source` | enum(`wazuh`,`direct`,`seeder`) | NOT NULL |
| `kind` | TEXT | NOT NULL. Dotted taxonomy: `auth.failed`, `auth.succeeded`, `session.started`, `session.ended`, `process.created`, `process.exited`, `file.created`, `network.connection`, etc. |
| `raw` | JSONB | NOT NULL. The original shape, as received |
| `normalized` | JSONB | NOT NULL. Canonical fields for this `kind` (contract below) |
| `dedupe_key` | TEXT | NULL. Optional idempotency key from the adapter |

**Indexes:** `(occurred_at DESC)`, `(kind, occurred_at DESC)`, GIN on `normalized`, UNIQUE `(source, dedupe_key) WHERE dedupe_key IS NOT NULL`.

**`normalized` JSONB contract by `kind` (initial set):**
- `auth.failed` / `auth.succeeded`: `{user, source_ip, auth_type, reason?, target?}`
- `session.started` / `session.ended`: `{user, host, session_id, logon_type?}`
- `process.created`: `{host, user?, pid, ppid, image, cmdline, cmdline_decoded?}`
- `process.exited`: `{host, pid, exit_code?}`
- `file.created`: `{host, path, user?, sha256?}`
- `network.connection`: `{host, src_ip, dst_ip, dst_port, proto, user?}`

Fields in `normalized` are strings unless typed in the contract. Adapters are responsible for populating this shape.

---

## 3. `event_entities` (junction)

Relates events to the entities involved in them with a role. Lets the correlator do efficient entity-scoped queries without scanning JSONB.

| Column | Type | Notes |
|---|---|---|
| `event_id` | UUID FK `events(id)` ON DELETE CASCADE | |
| `entity_id` | UUID FK `entities(id)` ON DELETE RESTRICT | |
| `role` | enum(`actor`,`target`,`source_ip`,`host`,`process`,`parent_process`,`file`,`observable`) | |

**PK:** `(event_id, entity_id, role)`.
**Indexes:** `(entity_id, event_id)` for entity-timeline queries.

---

## 4. `detections`

A rule fire against a specific event. One event can produce zero or many detections.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `event_id` | UUID FK `events(id)` ON DELETE CASCADE | |
| `rule_id` | TEXT | NOT NULL. E.g. `sigma.windows.powershell.encoded` or `py.auth.failed_burst` |
| `rule_source` | enum(`sigma`,`py`) | NOT NULL |
| `rule_version` | TEXT | NOT NULL. Semver or git-sha; tracks rule evolution |
| `severity_hint` | enum(`info`,`low`,`medium`,`high`,`critical`) | NOT NULL |
| `confidence_hint` | NUMERIC(3,2) | NOT NULL. 0.00–1.00 |
| `attack_tags` | TEXT[] | NOT NULL default `'{}'`. Entries like `T1078`, `T1059.001` |
| `matched_fields` | JSONB | NOT NULL default `'{}'`. Which event fields triggered the rule (for explainability) |
| `created_at` | TIMESTAMPTZ | NOT NULL default `now()` |

**Indexes:** `(rule_id, created_at DESC)`, `(event_id)`, GIN on `attack_tags`.

---

## 5. `incidents`

The product's center of gravity.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `title` | TEXT | NOT NULL |
| `kind` | enum(`identity_compromise`,`endpoint_compromise`,`identity_endpoint_chain`,`unknown`) | NOT NULL |
| `status` | enum(`new`,`triaged`,`investigating`,`contained`,`resolved`,`closed`,`reopened`) | NOT NULL default `'new'` |
| `severity` | enum(`info`,`low`,`medium`,`high`,`critical`) | NOT NULL |
| `confidence` | NUMERIC(3,2) | NOT NULL |
| `rationale` | TEXT | NOT NULL. Human-readable explanation; rewritten on incident growth |
| `opened_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `updated_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `closed_at` | TIMESTAMPTZ | NULL |
| `correlator_version` | TEXT | NOT NULL. Which version of correlator logic built/last-grew this |
| `correlator_rule` | TEXT | NOT NULL. Which rule opened the incident (e.g. `identity_endpoint_chain`) |
| `dedupe_key` | TEXT | NULL. For open-or-grow semantics (see below) |

**Indexes:** `(status, severity, opened_at DESC)`, `(updated_at DESC)`, UNIQUE `(dedupe_key) WHERE dedupe_key IS NOT NULL`.

**`dedupe_key` semantics:** the correlator computes a deterministic key (e.g. `identity_endpoint_chain:alice@corp.local:2026-04-19T00`) so that re-processing the same events doesn't open duplicate incidents; instead it grows the existing one.

---

## 6. `incident_events`, `incident_entities`, `incident_detections`, `incident_attack` (junctions)

### `incident_events`
| Column | Type | Notes |
|---|---|---|
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `event_id` | UUID FK `events(id)` ON DELETE RESTRICT | |
| `role` | enum(`trigger`,`supporting`,`context`) | NOT NULL. `trigger` = opened/grew the incident; `supporting` = confirms; `context` = nearby but not causal |
| `added_at` | TIMESTAMPTZ | NOT NULL default `now()` |

**PK:** `(incident_id, event_id)`.

### `incident_entities`
| Column | Type | Notes |
|---|---|---|
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `entity_id` | UUID FK `entities(id)` ON DELETE RESTRICT | |
| `role` | enum(`user`,`host`,`source_ip`,`observable`,`target_host`,`target_user`) | NOT NULL |
| `first_seen_in_incident` | TIMESTAMPTZ | NOT NULL default `now()` |

**PK:** `(incident_id, entity_id, role)`.

### `incident_detections`
| Column | Type | Notes |
|---|---|---|
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `detection_id` | UUID FK `detections(id)` ON DELETE RESTRICT | |
| `added_at` | TIMESTAMPTZ | NOT NULL default `now()` |

**PK:** `(incident_id, detection_id)`.

### `incident_attack`
| Column | Type | Notes |
|---|---|---|
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `tactic` | TEXT | NOT NULL. E.g. `TA0001` |
| `technique` | TEXT | NOT NULL. E.g. `T1078` |
| `subtechnique` | TEXT | NULL. E.g. `T1078.002` |
| `source` | enum(`rule_derived`,`correlator_inferred`) | NOT NULL |

**PK:** `(incident_id, tactic, technique, COALESCE(subtechnique, ''))`.

---

## 7. `incident_transitions`

Append-only status change log.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `from_status` | enum(incident status) | NULL for the initial open |
| `to_status` | enum(incident status) | NOT NULL |
| `actor` | TEXT | NOT NULL. `system` or analyst identifier |
| `reason` | TEXT | NULL |
| `at` | TIMESTAMPTZ | NOT NULL default `now()` |

**Indexes:** `(incident_id, at DESC)`.

---

## 8. `actions`

A proposed or executed response action.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `kind` | enum(`tag_incident`,`elevate_severity`,`flag_host_in_lab`,`quarantine_host_lab`,`invalidate_lab_session`,`block_observable`,`kill_process_lab`,`request_evidence`) | NOT NULL |
| `classification` | enum(`auto_safe`,`suggest_only`,`reversible`,`disruptive`) | NOT NULL |
| `params` | JSONB | NOT NULL. Per-kind contract (below) |
| `proposed_by` | enum(`system`,`analyst`) | NOT NULL |
| `proposed_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `status` | enum(`proposed`,`executed`,`failed`,`skipped`,`reverted`,`partial`) | NOT NULL default `'proposed'`. **`partial` (Phase 11)** = DB state committed but the Wazuh Active Response call failed or was skipped. Audit trail of what was attempted is load-bearing; we do not roll back. |

**Indexes:** `(incident_id)`, `(status)`.

**`params` JSONB contract by `kind`:**
- `tag_incident`: `{tags: [str]}`
- `elevate_severity`: `{to: severity_enum, reason: str}`
- `flag_host_in_lab` / `quarantine_host_lab`: `{host_entity_id: uuid}`
- `invalidate_lab_session`: `{user_entity_id: uuid, session_id?: str}`
- `block_observable`: `{observable_entity_id: uuid}`
- `kill_process_lab`: `{process_entity_id: uuid}`
- `request_evidence`: `{host_entity_id?: uuid, user_entity_id?: uuid, kinds: [str]}`

**Lab-scope enforcement:** before an executor transitions `status` to `executed`, every entity referenced in `params` (host/user/observable/process) must have a matching `(kind, natural_key)` row in `lab_assets`. Otherwise `status` → `skipped` with reason `out_of_lab_scope`.

---

## 9. `action_logs`

Append-only execution history.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `action_id` | UUID FK `actions(id)` ON DELETE CASCADE | |
| `executed_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `executed_by` | TEXT | NOT NULL. `system` or analyst identifier |
| `result` | enum(`ok`,`fail`,`skipped`,`partial`) | NOT NULL. **`partial` (Phase 11)** = DB state written successfully but Wazuh Active Response dispatch failed or was skipped. |
| `reason` | TEXT | NULL. Required if `result` != `ok` |
| `reversal_info` | JSONB | NULL. Enough info to reverse the action; contract depends on `action.kind`. For AR-dispatched actions also carries `ar_dispatch_status`, `ar_command`, `ar_agent_id`, and any manager error for the UI to render. |

**Indexes:** `(action_id, executed_at DESC)`.

---

## 10. `lab_assets`

Allowlist of systems/users/observables the response executor is permitted to act on.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `kind` | enum(`user`,`host`,`ip`,`observable`) | NOT NULL |
| `natural_key` | TEXT | NOT NULL. Must match `entities.natural_key` format |
| `registered_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `notes` | TEXT | NULL |

**Unique:** `(kind, natural_key)`.

---

## 11. `notes` (analyst annotations)

Optional in v1 but cheap to add and central to analyst UX.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `body` | TEXT | NOT NULL |
| `author` | TEXT | NOT NULL. Single-operator v1: always the operator |
| `created_at` | TIMESTAMPTZ | NOT NULL default `now()` |

**Indexes:** `(incident_id, created_at DESC)`.

---

## 12. Response state tables (Phase 9A)

These three tables back the response handlers that were upgraded from stub to real in migration `0005_response_state_tables`.

### `lab_sessions`
Tracks simulated user sessions on lab hosts. Populated by the `session.started` event extractor; consumed by `invalidate_lab_session`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_entity_id` | UUID FK `entities(id)` | the signed-in user |
| `host_entity_id` | UUID FK `entities(id)` | where the session is |
| `session_id` | TEXT | NULL. Optional provider session id |
| `opened_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `invalidated_at` | TIMESTAMPTZ | NULL. Set by `invalidate_lab_session`; cleared by revert |

### `blocked_observables`
Rows here are the source of truth for the **response → detection feedback loop**. When an analyst executes `block_observable`, the `blocked_observable` detector re-reads this table (Redis-cached 30s) for every subsequent event and fires `py.blocked_observable_match` on any hit.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `kind` | enum(`ip`,`domain`,`hash`) | NOT NULL. The `blockable_kind` enum (added in migration 0005) |
| `value` | TEXT | NOT NULL. Normalized lowercase for `ip`/`domain`, hex for `hash` |
| `active` | BOOLEAN | NOT NULL default `true`. Flip to `false` on revert — the detection stops firing immediately (cache invalidated) |
| `blocked_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `blocked_by_action_id` | UUID FK `actions(id)` | the action that created this block (for the audit trail back to the originating incident) |

**Unique:** `(kind, value) WHERE active = true`.

### `evidence_requests`
Analyst-facing triage checklist. `identity_compromise` incidents auto-propose a `triage_log` request. `kill_process_lab` auto-proposes a `process_list` request on the target host.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `incident_id` | UUID FK `incidents(id)` ON DELETE CASCADE | |
| `kind` | enum(`process_list`,`triage_log`,`file_snapshot`,`network_dump`) | NOT NULL (the `evidence_kind` enum) |
| `target_host_entity_id` | UUID FK `entities(id)` | NULL for incident-wide requests |
| `target_user_entity_id` | UUID FK `entities(id)` | NULL unless user-scoped |
| `status` | enum(`open`,`collected`,`dismissed`) | NOT NULL default `'open'` (the `evidence_status` enum) |
| `requested_at` | TIMESTAMPTZ | NOT NULL default `now()` |
| `resolved_at` | TIMESTAMPTZ | NULL. Set on transition to `collected` or `dismissed` |
| `payload_url` | TEXT | NULL. Reserved for future file-collection integration |
| `notes` | TEXT | NULL. Analyst notes at collection/dismissal time |

---

## 12b. Wazuh poller cursor (Phase 8)

### `wazuh_cursor`
Singleton row (id = `'singleton'`) holding the Wazuh indexer poller's `search_after` cursor so we resume exactly where we left off after a restart.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Always `'singleton'` |
| `search_after` | JSONB | NULL. The last OpenSearch `search_after` array. Serialized via `json.dumps()` + `CAST(:sa AS JSONB)` — asyncpg cannot encode a Python list directly to JSONB |
| `last_success_at` | TIMESTAMPTZ | NULL |
| `last_error` | TEXT | NULL. Populated on poller failure; cleared on next success |
| `events_ingested_total` | BIGINT | NOT NULL default 0. Monotonic counter for smoke tests |

Exposed read-only at `GET /v1/wazuh/status`.

---

## 13. Computation policies (explicit, not magical)

### Severity
Map tiers to integers: `info=0, low=1, medium=2, high=3, critical=4`.

```
severity_int = max(detection.severity_hint for detection in incident_detections)
if count(incident_detections) >= 3:                  severity_int += 1
if has_identity_detection and has_endpoint_detection: severity_int += 1
severity_int = min(severity_int, 4)  # cap at critical
```

`has_identity_detection` = any detection whose `rule_id` is in the identity rule family (e.g. `py.auth.*`, `sigma.auth.*`).
`has_endpoint_detection` = any detection whose `rule_id` is in the endpoint rule family (e.g. `py.process.*`, `sigma.windows.*`, `sigma.linux.*`).

### Confidence
```
base        = avg(detection.confidence_hint for detection in incident_detections)
bonus_rule  = 0.10  if correlator_rule == 'identity_endpoint_chain' else 0
bonus_attck = 0.05 * min(3, count(distinct tactics in incident_attack))
bonus_ent   = 0.05  if any entity appears in >= 2 incident_events else 0
confidence  = min(1.00, base + bonus_rule + bonus_attck + bonus_ent)
```

### Rationale
Each correlator rule owns a Python-format template. On each incident open or grow:
1. Collect template fields from contributing events/entities.
2. Render a fresh rationale string.
3. Overwrite `incidents.rationale`.
4. Audit trail lives in `incident_transitions` (for status) and in `incident_events.added_at` (for which events contributed when).

We do **not** append rationale history inside `incidents.rationale`. The current rationale is always coherent; history is recoverable from the junction tables.

---

## 14. What's deliberately not in this schema (v1)

- **Raw-log archive table.** Raw logs stay in Wazuh's indexer. We keep a JSONB snapshot per ingested event in `events.raw`, which is enough for explainability without duplicating a SIEM.
- **Users/roles/auth.** Single operator, local, v1. Add an `app_users` table when we introduce real auth (ADR-worthy).
- **Multi-tenancy.** No `tenant_id` columns. Out of scope.
- **Enrichment cache tables.** If we add TI enrichment later, it gets its own ADR and its own tables.
- **Correlator state.** Lives in Redis (ephemeral by design). Durable truth = Postgres.

---

## 15. Scenario coverage check

This schema must express every moment in `docs/scenarios/identity-endpoint-chain.md`. Cross-reference:

- 6 `auth.failed` events → 6 `events` rows, each with `event_entities` (actor=alice, source_ip=203.0.113.7). ✓
- `py.auth.failed_burst` detection → 1 `detections` row tagged `T1110`, `T1110.003`. ✓
- `auth.succeeded` from new source → `events` row + `py.auth.anomalous_source_success` detection. ✓
- Incident opens → `incidents` row (kind=`identity_compromise`), junction rows for trigger events, detections, entities (alice, 203.0.113.7), ATT&CK rows (T1110, T1078). ✓
- `session.started` → `events` row + `incident_events` (role=`supporting`). ✓
- `process.created` encoded PowerShell → `events` row + `sigma.windows.powershell.encoded` detection + `incident_events` (role=`trigger` for growth). ✓
- Incident grows → `incidents.kind` updated to `identity_endpoint_chain`, `rationale` rewritten, `severity`/`confidence` recomputed, new ATT&CK rows (T1059, T1059.001, T1027), host entity added to `incident_entities`. ✓
- Auto tag action → `actions` row (classification=`auto_safe`, status=`executed`) + `action_logs` row. ✓
- Suggested flag-host action → `actions` row (status=`proposed`); on analyst confirm → status=`executed`, `action_logs` row, `entities.attrs.lab_flagged = true` for the host. ✓
- Analyst walks `new → triaged → investigating → contained` → 3 `incident_transitions` rows. ✓

No gaps.
