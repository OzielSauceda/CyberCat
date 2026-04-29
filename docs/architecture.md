# Architecture — CyberCat

Canonical system design. This is the document future sessions should read when they need to know *how CyberCat is structured*. For *why*, see the ADRs. For *what's done*, see `PROJECT_STATE.md`.

---

## 1. One-paragraph summary

CyberCat ingests security telemetry from one or more pluggable sources (default: a custom Python sidecar agent that ships sshd events; optional: Wazuh), normalizes it into a canonical internal event/entity model, runs detection logic (Sigma + custom Python detectors), correlates related signals into incidents, tracks incident lifecycle and evidence in PostgreSQL, and lets an analyst investigate and execute guarded response actions through a Next.js UI. Redis handles ephemeral coordination. The custom application layer — correlation, incident model, response policy, analyst UX — is the product. Wazuh is upstream telemetry, not the product.

**Current state (Phases 1–16.10 + Phase 18 verified + merged to main, Phase 17 in-flight, 2026-04-29):** Default stack now boots in ~900 MB resident (vmmemWSL 2.8 GB, down from ~4 GB) thanks to the Phase 16 custom telemetry agent. All 8 action kinds have real handlers. `quarantine_host_lab` and `kill_process_lab` optionally dispatch real Wazuh Active Response (Phase 11, flag-gated). Phase 12 added three hand-drawn SVG panels; **Phase 18 redesigned two of them** — the kill-chain panel ("The route") now shows only matched ATT&CK tactics as stamped stations on an animated path with a pulsing "HERE" marker on the latest, and the timeline panel ("The reel") is now a multi-lane reel (identity / session / endpoint / network) with a playhead sweep, inline labels on triggers and detections, and red-string entity threads connecting events that share a user or host. Phase 13 replaced polling with SSE streaming (Redis pub/sub fan-out, refetch-on-notify). Phase 14.1–14.4 adds multi-operator auth: `users` + `api_tokens` tables, bcrypt+itsdangerous session cookies, Bearer token path, three roles (`admin`/`analyst`/`read_only`), HMAC-signed cookies, route gating (`require_analyst` on mutations, `require_user` on reads), `actor_user_id` FKs on every audit write, and OIDC opt-in (`/v1/auth/oidc/login` + callback, JIT user provisioning, authlib JWT validation). Feature-flagged: `AUTH_REQUIRED=false` by default so all existing tests and demos run unchanged. **Phase 15 adds Recommended Response Actions**: a static two-level mapping engine (incident_kind → base candidates; ATT&CK technique prefix → priority boost) returns up to 4 ranked, pre-filled action suggestions per incident; new `RecommendedActionsPanel` on the incident detail page surfaces them with a "Use this" button that opens `ProposeActionModal` pre-populated. **Phase 18 adds plain-language layers throughout**: a centralized `frontend/app/lib/labels.ts` enum-to-friendly-label module + `PlainTerm` hybrid component, an extended glossary, and an `incidents.summary` column (nullable, Alembic 0008) populated by every correlator rule and exposed on `IncidentSummary` / `IncidentDetail` / `RecommendedActionOut`. The frontend leads with `summary`; the original technical `rationale` lives behind a "Show technical detail" expander to satisfy CLAUDE.md §2 explainability. **174 tests green** (incl. `test_summary_jargon.py` asserting recommended-action summaries are free of rule_ids and ATT&CK technique codes), smoke_test_phase8 27/27, smoke_test_phase9a 14/14, smoke_test_phase10 15/15, smoke_test_phase11 8/8, smoke_test_phase13 8/8, smoke_test_phase15 19/19.

## 2. Conceptual layers

```
┌──────────────────────────────────────────────────────────────────────┐
│  Analyst Frontend (Next.js + TypeScript)                             │
│  incidents · entity detail · detections · lab assets · ATT&CK        │
│  actions dashboard · evidence requests · blocked observables badge   │
└──────────────────────────────▲───────────────────────────────────────┘
                               │  typed REST (OpenAPI → openapi-typescript)
┌──────────────────────────────┴───────────────────────────────────────┐
│  Product API (FastAPI)                                               │
│  /incidents  /entities  /events  /detections  /responses             │
│  /attack/catalog  /lab/assets  /evidence-requests  /blocked-observables│
│  /wazuh/status                                                       │
└───▲──────────▲─────────────▲────────────────▲───────────────────────┘
    │          │             │                │
┌───┴────┐ ┌───┴──────┐ ┌────┴─────────┐ ┌────┴──────────────┐
│Response│ │Correlator│ │Detection eval│ │ Normalizer        │
│Policy  │ │(identity_│ │ Python rules │ │ raw → canonical   │
│Engine  │ │compromise│ │ Sigma rules  │ │ event/entity      │
│(8 kinds│ │ endpoint_│ │ blocked_obs  │ │ session extractor │
│ 5 real)│ │ join +   │ │ ← feeds from │ │                   │
│        │ │ standalone│ │   responses  │ │                   │
└───▲────┘ └───▲──────┘ └────▲─────────┘ └────▲──────────────┘
    │          │             │                │
    │          │             │          ┌─────┴──────────────┐
    │          │             │          │ Ingest adapters    │
    │          │             │          │ Wazuh poller ·     │
    │          │             │          │ direct API         │
    │          │             │          └─────▲──────────────┘
    │          │             │                │
    │          │             │           ┌────┴─────┐
    │          │             │           │  Wazuh   │
    │          │             │           │ (manager │
    │          │             │           │  +agents)│
    │          │             │           └──────────┘
    │          │             │
    │     ┌────┴─────┐   ┌───┴──────────────────────┐
    │     │  Redis   │   │ Postgres (truth)          │
    │     │(ephemeral│   │ incidents · entities      │
    │     │ windows, │   │ detections · evidence     │
    │     │ dedup,   │   │ actions · action_logs     │
    │     │ cooldown,│   │ lab_sessions              │
    │     │ blocked_ │   │ blocked_observables       │
    │     │ obs cache│   │ evidence_requests         │
    │     └──────────┘   └──────────────────────────┘
    │
    └──► Lab response actions (quarantine flag, kill_process, session
         invalidate, observable block, evidence request — all logged,
         reversible or disruptive as classified, lab-scoped)
```

## 3. Components

### 3.1 Telemetry sources (pluggable)

CyberCat is **telemetry-source-agnostic**. Every downstream component (normalizer, detection rules, correlator, response policy, UI) keys on the canonical `Event` shape — whether the event arrived via the custom agent or via the Wazuh poller is recorded in `Event.source` (`EventSource.direct` / `EventSource.wazuh` / `EventSource.seeder`) and otherwise irrelevant.

Two sources are wired in. Either, both, or neither can be active at runtime:

- **Custom telemetry agent (`agent/`, `cct-agent` container)** — **default since Phase 16.** A standalone Python 3.12 sidecar that runs **three parallel tail loops** against the lab-debian container's `/var/log` (shared read-only via the `lab_logs` named volume) and feeds a single shared `Shipper` queue:
  1. **sshd source** (Phase 16) — tails `/var/log/auth.log`, parses with `agent/cct_agent/parsers/sshd.py`, emits `auth.failed`, `auth.succeeded`, `session.started`, `session.ended`.
  2. **auditd source** (Phase 16.9) — tails `/var/log/audit/audit.log`, assembles EXECVE+SYSCALL+PROCTITLE/PATH groups via the stateful `AuditdParser` (`agent/cct_agent/parsers/auditd.py`, buffers by `audit(ts:event_id)`, flushes on EOE), and runs them through `TrackedProcesses` (`agent/cct_agent/process_state.py`, bounded LRU of 4096 PIDs) to enrich `process.created` events with `parent_image` and gate `process.exited` to PIDs we previously saw start.
  3. **conntrack source** (Phase 16.10) — tails `/var/log/conntrack.log`, written by `conntrack -E -e NEW -o timestamp -o extended -o id` running inside lab-debian (under its existing `NET_ADMIN` capability). Stateless single-line parser (`agent/cct_agent/parsers/conntrack.py`) emits `network.connection` events from `[NEW]` records only; loopback (`127.0.0.0/8`, `::1`) and link-local (`169.254/16`, `fe80::/10`) records are dropped at the parser. Dedupe uses conntrack `id=` when present, falls back to a SHA256 of the raw line.
  Each source owns its own checkpoint (`checkpoint.json` for sshd, `audit-checkpoint.json` for auditd, `conntrack-checkpoint.json` for conntrack; all under `/var/lib/cct-agent/`; all handle rotation by inode change and truncation by `size < offset`). Events are built by `agent/cct_agent/events.py` (`source="direct"`) and POSTed to `/v1/events/raw` with a Bearer token. Bounded in-memory queue with drop-oldest on overflow; exponential backoff on 5xx and network errors; **never retries 4xx** (malformed payloads are logged and dropped). The auditd and conntrack sources are gated by `CCT_AUDIT_ENABLED` / `CCT_CONNTRACK_ENABLED` plus a `path.exists()` check at startup, so the agent degrades gracefully (with a warning) when the kernel audit or conntrack subsystem is unavailable (e.g. Docker Desktop on Windows). See ADR-0011, ADR-0012, ADR-0013.

  **Per-source canonical event kinds:**

  | Source | Kinds emitted |
  |---|---|
  | sshd     | `auth.failed`, `auth.succeeded`, `session.started`, `session.ended` |
  | auditd   | `process.created`, `process.exited` |
  | conntrack | `network.connection` |
- **Wazuh adapter (`backend/app/ingest/wazuh_*.py`)** — opt-in via `--profile wazuh`. Asyncio pull-mode poller queries the Wazuh Indexer REST API via `_search` + `search_after` cursor; alert → normalized-event mapping in `wazuh_decoder.py`; cursor state in `wazuh_cursor` Postgres table. The decoder handles three event kinds: `auth.failed` / `auth.succeeded` (sshd) and `process.created` from auditd EXECVE (Linux) and Sysmon EventID 1 (Windows). The bridge is gated by `WAZUH_BRIDGE_ENABLED` (defaults to `false` since Phase 16) so the dormant code path doesn't try to reach a manager that isn't there. See ADR-0004 (bridge mechanism), ADR-0011 (default-source inversion).
- **Direct API adapter** — `POST /v1/events/raw` is *also* used by the lab seeder, smoke tests, and the cct-agent. The agent is, conceptually, just a long-lived API client.

All three paths converge on the same `ingest_normalized_event` pipeline (`backend/app/ingest/pipeline.py`): dedup → persist → entity extract → detect → correlate → commit → auto-actions. Adapters do *no* product logic. They only hand off canonical events to the normalizer.

**Default deployment shape (Phase 16):** `./start.sh` brings up postgres, redis, backend, frontend, lab-debian, and cct-agent — six containers, ≈ 900 MB resident (measured 2026-04-28: cct-agent 25 MB, redis 8, postgres 59, lab-debian 47, backend 142, frontend 622 = 902 MB total). The Wazuh stack (manager + indexer + the lab-debian wazuh-agentd) is opt-in via `./start.sh --profile wazuh` and adds ~1.8 GB. Both modes drive the same detection/correlation/response code paths. See `docs/runbook.md` § "Telemetry sources" for operational details.

### 3.2 Normalizer (`backend/app/ingest/normalizer.py`, `entity_extractor.py`)
- `normalizer.py` — validates raw events against a per-kind required-field registry.
- `entity_extractor.py` — upserts entities (user, host, ip, process, file, observable) from normalized event fields using PostgreSQL `ON CONFLICT DO UPDATE`. Creates `event_entities` junction rows linking events to their entities.

### 3.3 Detection evaluation (`backend/app/detection/`)
- `engine.py` — `@register()` decorator, `run_detectors()` (persists fired detections).
- `rules/` — Python detectors:
  - `auth_failed_burst.py` — ≥4 `auth.failed` for same user in 60s, Redis-backed.
  - `auth_anomalous_source_success.py` — successful auth from unknown source with prior failures.
  - `process_suspicious_child.py` — encoded PowerShell, office-spawns-shell, rundll32+script.
  - `blocked_observable.py` — `py.blocked_observable_match` fires when an ingested event's IP/domain/hash appears in the `blocked_observables` table. Redis-cached (30s TTL) to avoid per-event DB reads. This creates a feedback loop: a response action (block_observable) changes what the detection engine alerts on.
- `sigma/` — Sigma parser, compiler, field_map. Sigma pack with curated rules co-fires with Python detectors on `process.created` events.

### 3.4 Correlator (`backend/app/correlation/`)
- **This is the heart of the product.**
- `engine.py` — `@register()` decorator, `run_correlators()`.
- `rules/identity_compromise.py` — opens incidents on `py.auth.anomalous_source_success`; deduped by `identity_endpoint_chain:{user}:{hour_bucket}`.
- `rules/endpoint_compromise_join.py` — extends an open identity_compromise incident for the same user when `py.process.suspicious_child` fires within a 30-minute window.
- `rules/endpoint_compromise_standalone.py` — opens a separate `endpoint_compromise` incident (medium/0.60) when a suspicious process fires without a corroborating identity chain. Deduped by host+hour bucket via Redis SETNX.
- `extend.py` — `extend_incident()` helper; idempotent junction growth via `ON CONFLICT DO NOTHING`.
- `auto_actions.py` — proposes and auto-executes `auto_safe` actions post-commit. Also auto-proposes `request_evidence` (suggest_only) on `identity_compromise` incidents so the analyst always has a triage checklist waiting.

### 3.5 ATT&CK catalog (`backend/app/attack/`)
- `catalog.json` — hand-curated ATT&CK v14.1 subset, **37 entries** covering identity + endpoint + lateral movement + persistence paths (grew from 24 in Phase 9A).
- `catalog.py` — module-level load-once; exports `get_catalog()` and `get_entry(id)`.
- Served at `GET /v1/attack/catalog`. Frontend caches in a module-level Map singleton via `useAttackEntry` hook.

### 3.6 Incident model
- Owned by the DB schema (`incident_events`, `incident_entities`, `incident_detections`, `incident_attack`, `incident_transitions`, `notes`).
- Lifecycle: `new → triaged → investigating → contained → resolved → closed` (with `reopened` reserved).
- Every incident retains: contributing events, fired detections, linked entities (with roles), ATT&CK rows, correlator rationale, status transitions, analyst notes, response actions.

### 3.7 Response policy + executor (`backend/app/response/`)
- `policy.py` — pure `classify(kind)` → `ClassificationDecision(classification, reason)`. Every `ActionKind` maps to `auto_safe`, `suggest_only`, `reversible`, or `disruptive`.
- `executor.py` — `propose_action`, `execute_action`, `revert_action`. Lab-scope check at propose + execute time. Revert is guarded: only `reversible` actions can be reverted; `disruptive` returns 409.
- `handlers/` — all 8 action kinds have real handlers:

| Handler | Classification | DB state |
|---|---|---|
| `tag_incident` | auto_safe | `incidents.tags` updated |
| `elevate_severity` | auto_safe | `incidents.severity` updated |
| `flag_host_in_lab` | reversible | `LabAsset.notes` marker; revert clears it |
| `quarantine_host_lab` | disruptive | `LabAsset.notes` quarantine marker + incident note |
| `kill_process_lab` | disruptive | `EvidenceRequest(process_list)` auto-created |
| `invalidate_lab_session` | reversible | `LabSession.invalidated_at = now()`; revert clears |
| `block_observable` | reversible | `BlockedObservable(active=True)`; detection engine checks on every event; revert sets `active=False` |
| `request_evidence` | suggest_only | `EvidenceRequest` row inserted, `status=open` |

**Wazuh Active Response dispatch (Phase 11, shipped).** `quarantine_host_lab` and `kill_process_lab` now optionally dispatch real Active Response calls behind the `WAZUH_AR_ENABLED` flag (default `false`, so existing demos remain safe). The AR dispatcher (`backend/app/response/dispatchers/wazuh_ar.py`) handles token caching (270s TTL), single 401 re-auth, 5s connect / 10s read timeouts, and never logs the Authorization header. `quarantine_host_lab` dispatches Wazuh's built-in `firewall-drop0` → real `iptables -I INPUT DROP` rule. `kill_process_lab` dispatches a custom `kill-process.sh` script that reads `/proc/<pid>/cmdline`, validates against the requested process name (defeating PID reuse), then `kill -9`s. A new `partial` action result is used when DB state commits but the AR call fails — rendered in the UI as an amber badge with a tooltip. See ADR-0005 (handler shape) and ADR-0007 (AR dispatch).

**Recommended response actions (Phase 15, shipped).** `backend/app/response/recommendations.py` is a pure function (`recommend_for_incident`) over an `Incident` + its loaded entities/attack/actions that returns a sorted list of `RecommendedAction` candidates. Two-level mapping: **Level 1** — `IncidentKind` → base candidate list (`identity_compromise` → `block_observable`, `invalidate_lab_session`, `flag_host_in_lab`, `request_evidence`; `endpoint_compromise` → `quarantine_host_lab`, `block_observable`, …; `identity_endpoint_chain` → all four; `unknown` → `request_evidence` only). **Level 2** — ATT&CK technique prefix → priority boost (`T1110` Brute Force → +20 to `block_observable`; `T1078` Valid Accounts → +20 to `invalidate_lab_session`; `T1059` C&S Interpreter → +10 to `quarantine_host_lab`; `T1021` Lateral Movement → +20 to `quarantine_host_lab`; `T1071`/`T1571` C2 → +20 to `block_observable`). Match is by `technique.startswith(prefix)` so subtechniques (e.g. `T1110.003`) inherit. Excluded kinds (never recommended): `tag_incident`, `elevate_severity`, `kill_process_lab`. Already-executed-and-not-reverted actions are filtered out, with `block_observable` matched on `(kind, params.value)` only (so two block actions on different IPs are distinct candidates). Each candidate is built from incident-role-bucketed entities (user, host, source_ip, observable); candidates whose required entity is missing are dropped — the recommender only emits *valid, executable* suggestions. Exposed at `GET /v1/incidents/{id}/recommended-actions` (read endpoint, all roles). UI: new `RecommendedActionsPanel` renders above `ActionsPanel` with classification badges, humanized labels, rationale, EntityChip targets, and a "Use this" button that opens `ProposeActionModal` pre-populated via a new `prefill?: { kind, form }` prop. Modal ownership is lifted to `page.tsx` so both panels drive a single modal instance; the panel refetches when `incident.actions` change (driven by SSE-triggered incident refetch via a stringified `refreshKey`). See ADR-0010 (recommendations engine).

### 3.8 Product API (`backend/app/api/`)
- FastAPI routers: `/v1/incidents` (incl. `/v1/incidents/{id}/recommended-actions` — Phase 15), `/v1/entities`, `/v1/events`, `/v1/detections`, `/v1/responses`, `/v1/attack/catalog`, `/v1/lab/assets`, `/v1/evidence-requests`, `/v1/blocked-observables`, `/v1/wazuh/status`.
- Auth router (`backend/app/auth/router.py`): `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me`, `GET /v1/auth/config`, `POST /v1/auth/tokens`, `DELETE /v1/auth/tokens/{id}`, `GET /v1/auth/users`, `PATCH /v1/auth/users/{id}/role`, `GET /v1/auth/oidc/login`, `GET /v1/auth/oidc/callback`.
- TypeScript client generated via `openapi-typescript` (`npm run gen:api`) → `frontend/app/lib/api.generated.ts`. Manual fetch helpers in `api.ts` sit on top.
- `ErrorEnvelope` declared on all mutation endpoints for consistent error structure.

### 3.9 Auth package (`backend/app/auth/`)
- `models.py` — `User` (id, email citext, password_hash, oidc_subject, role enum, is_active, token_version), `ApiToken` (sha256 digest only; plaintext returned once at creation).
- `security.py` — bcrypt hash/verify, itsdangerous HMAC session sign/verify, SHA-256 token hash/generate.
- `dependencies.py` — `get_current_user` (cookie → bearer token fallback; returns `SystemUser` sentinel when `AUTH_REQUIRED=false`); `require_user`, `require_analyst`, `require_admin` composable deps; `resolve_actor_id` (real user UUID or `legacy@cybercat.local` UUID).
- `oidc.py` — `OIDCConfig` (cached discovery + JWKS); `discover_oidc()` (startup fetch of `/.well-known/openid-configuration`); `make_authorization_url()` (state+nonce in signed itsdangerous cookie); `verify_state()`; `exchange_code_for_user_info()` (token exchange + authlib JWT validation); `upsert_oidc_user()` (lookup by oidc_subject → email → JIT create with role=read_only).
- `router.py` — all auth endpoints including OIDC login/callback.
- Feature flag: `AUTH_REQUIRED=false` (default) → `SystemUser` sentinel returned by all deps → zero change to existing tests and demos. `AUTH_REQUIRED=true` → real cookie/bearer enforcement.

### 3.10 Frontend (`frontend/app/`)
- Next.js 15 App Router + TypeScript + Tailwind.
- **Pages:**
  - `/login` — email/password form; "Sign in with SSO" button conditionally shown when `authConfig.oidc_enabled`; redirects to `?next=` on success.
  - `/incidents` — list with status/severity filters, 10s polling, load-more pagination.
  - `/incidents/[id]` — detail: timeline (by-entity + chronological toggle), detections, entities (clickable chips), ATT&CK (named tags), **recommended response panel (Phase 15) → response actions**, status transitions, notes, evidence requests panel.
  - `/entities/[id]` — entity detail: attrs, recent events, related incidents. Shows `BlockedObservablesBadge` if the entity's observable is currently blocked.
  - `/detections` — filterable detection list (source, rule_id, since); routes to linked incident.
  - `/actions` — top-level dashboard for all response actions across all incidents.
  - `/lab` — lab assets CRUD: table, add-asset form, ConfirmDialog delete.
- **Shared components:** `SeverityBadge`, `StatusPill`, `ConfidenceBar`, `RelativeTime`, `AttackTag`, `EntityChip`, `Panel`, `JsonBlock`, `EmptyState`, `ErrorState`, `Skeleton`, `Toast`, `ConfirmDialog`, `TransitionMenu`, `ActionClassificationBadge`, `WazuhBridgeBadge`, `EvidenceRequestsPanel`, `BlockedObservablesBadge`, `UserBadge`.
- **Incident-page panels** (under `frontend/app/incidents/[id]/`): `ActionsPanel`, `AttackKillChainPanel`, `EntityGraphPanel`, `IncidentTimelineViz`, `NotesPanel`, `ProposeActionModal` (Phase 15: `prefill?: { kind, form }` prop), `RecommendedActionsPanel` (Phase 15: new).
- **Lib:** `api.ts` (typed REST client + `credentials: include` + 401→login redirect; Phase 15 adds `RecommendedAction` type + `getRecommendedActions(incidentId)`), `api.generated.ts` (OpenAPI-generated types), `usePolling.ts` (visibility-aware polling), `attackCatalog.ts` (singleton catalog cache + `useAttackEntry` hook), `transitions.ts` (allowed-transition map), `actionForms.ts` (all 8 action kinds registered with form schemas), `auth.ts` (login/logout/getMe/getAuthConfig), `SessionContext.tsx` (`SessionProvider`, `useSession()`, `useCanMutate()`).

## 4. Data stores

### 4.1 PostgreSQL — durable truth
Tables (migration chain 0001–0007):
- Core: `entities`, `events`, `event_entities`, `detections`
- Incident: `incidents`, `incident_events`, `incident_entities`, `incident_detections`, `incident_attack`, `incident_transitions`, `notes`
- Response: `actions`, `action_logs`
- Lab: `lab_assets`, `lab_sessions`
- Response state (Phase 9A): `blocked_observables`, `evidence_requests`
- Infra: `wazuh_cursor` (singleton Wazuh poller cursor)
- Auth (Phase 14): `users` (id, email citext unique, password_hash, oidc_subject, role, is_active, token_version), `api_tokens` (id, user_id FK, name, token_hash bytea unique, last_used_at, revoked_at). Audit FK columns added (nullable): `actor_user_id` on `action_logs`, `incident_transitions`, `notes`; `collected_by_user_id` + `dismissed_by_user_id` on `evidence_requests`; `created_by_user_id` on `lab_assets`. Backfill sentinel: `legacy@cybercat.local` (role=analyst, is_active=false) pre-populated so all historical audit rows have a valid actor UUID.

### 4.2 Redis — ephemeral coordination
Used for: sliding detection windows (auth failure counts), dedup keys (60s TTL on event ingestion), rule cooldowns (120s post-detection), correlation dedup keys (multi-hour SETNX for incident dedup), `blocked_observables` query cache (30s TTL — avoids per-event DB reads). **Never** the system of record.

## 5. Data flow (happy path)

**Ingest → detect → correlate → respond:**

1. Wazuh (or the lab seeder) emits a raw event via `POST /v1/events/raw`.
2. Normalizer validates shape, writes `Event`, upserts entities, writes `event_entities` junctions. `session.started` events also create `LabSession` rows linking user+host entities.
3. Detection engine runs all registered Python detectors + Sigma rules against the normalized event → writes `Detection` records. Includes `blocked_observable` check (Redis-cached query of `blocked_observables` table).
4. Correlator runs against each fired detection:
   - `identity_compromise` — opens a new incident on `py.auth.anomalous_source_success`; deduped by user+hour bucket.
   - `endpoint_compromise_join` — finds an open identity_compromise incident for same user within 30 min, extends it with `extend_incident()`.
   - `endpoint_compromise_standalone` — opens a separate medium-severity incident when a suspicious process fires without a corroborating identity chain; deduped by host+hour.
5. `auto_actions.py` runs post-commit: `auto_safe` actions execute immediately. `identity_compromise` incidents also get an auto-proposed `request_evidence` (suggest_only) for the analyst.
6. Frontend polls `GET /v1/incidents/{id}` (5s) and `GET /v1/incidents` (10s), rendering live updates.

**Response feedback loop:**

7. Analyst proposes `block_observable` → executes → `BlockedObservable(active=True)` written, Redis cache invalidated.
8. Next event ingested with that IP/domain → `blocked_observable` detector queries Redis/DB → fires `py.blocked_observable_match` → new Detection row on the incident.
9. Analyst reverts → `active=False`, cache cleared → no more matches.

## 6. Incident lifecycle

```
new ──► triaged ──► investigating ──► contained ──► resolved ──► closed
                                          │
                                          └──► reopened (back to investigating)
```

Transitions are explicit API calls (`POST /v1/incidents/{id}/transitions`). Every transition is logged with actor (`system` or `analyst`), timestamp, reason. Response actions are separately tracked and can occur in any open state.

## 7. Explainability contract

Every incident answers these from the DB alone:
- What raw events contributed? (`incident_events` join)
- What detections fired? (`incident_detections` join)
- What entities are involved and how? (`incident_entities` with roles)
- What ATT&CK tactics/techniques apply? (`incident_attack` join)
- Why did the correlator open/grow this incident? (`incidents.rationale` for the technical explanation; `incidents.summary` for a plain-language version that the UI leads with)
- What response actions ran or were proposed? (`actions` + `action_logs`)
- How did status evolve? (`incident_transitions`)
- What evidence was requested and what happened to it? (`evidence_requests`)
- Which observables are currently blocked and why? (`blocked_observables` + linking `action_logs`)

If any of these ever becomes un-answerable, it's an architectural bug.

## 8. Streaming layer

`GET /v1/stream` is a Server-Sent Events endpoint that pushes lightweight notifications when domain state changes. See [`docs/streaming.md`](streaming.md) for the full event taxonomy and ops debugging.

**Architecture:**

```
Domain action → db.commit() → publish(StreamEvent) → redis.publish(cybercat:stream:<topic>)
                                                              │
                                                 (one shared Redis subscriber per process)
                                                              │
                                              fan out via asyncio.Queue per SSE connection
                                                    │            │
                                              browser tab A   browser tab B
                                               EventSource     EventSource
                                                    │
                                               useStream hook → refetch on notify
```

- `backend/app/streaming/publisher.py` — `publish(event_type, data)` builds the envelope and calls `redis.publish`. Never raises.
- `backend/app/streaming/bus.py` — `EventBus` holds one Redis pubsub subscriber; fans out to registered per-connection `asyncio.Queue`s.
- `backend/app/api/routers/streaming.py` — `GET /v1/stream` wraps the async generator in a `StreamingResponse`.
- Frontend: `useStream` hook replaces `usePolling` on all main pages; keeps 60s safety-net polling while SSE is live.

## 9. Deployment shape

- `infra/compose/docker-compose.yml`:
  - implicit core (always-on): `postgres`, `redis`, `backend`, `frontend`
  - `--profile agent` (default since Phase 16): adds `lab-debian` + `cct-agent` (custom telemetry agent). `start.sh` defaults to this profile when no `--profile` is passed and provisions the agent's API token on first run.
  - `--profile wazuh`: adds `lab-debian` + `wazuh-manager` + `wazuh-indexer` (Phase 8; requires cert setup — see runbook). Both profiles can be active simultaneously.
- Everything bound to localhost. No production hardening in v1.
- Alembic runs as part of backend startup (`start.sh` calls `alembic upgrade head` then starts uvicorn). Migration chain: 0001→0002→0003→0004→0005.
- Frontend is a build image (no volume mount) — adding new pages requires `docker compose build frontend`.
- OpenAPI spec is exported from the running container (`scripts/dump_openapi.py`) and committed. Frontend types regenerated via `npm run gen:api` or `npm run gen:api:file`.

## 9. What we intentionally do not build

- Our own endpoint agent. Wazuh already does agent work; we consume it.
- Our own log store. Postgres handles structured product data; raw log volume stays in Wazuh.
- A rule language. Sigma covers pattern rules; Python covers rate/sequence checks. No custom DSL.
- A full ATT&CK knowledge base. We maintain a hand-curated 37-entry subset. Full STIX import is not on the roadmap.
- Enterprise auth beyond three roles. CyberCat now has local password auth + HMAC session cookies + API tokens + three roles (admin/analyst/read_only). SAML, SCIM, MFA, fine-grained per-resource ACLs, and multi-tenancy are out of scope. OIDC opt-in (Phase 14.4) covers Google Workspace, Okta, Auth0, Keycloak — the realistic SOC provider list.
- A Wazuh dashboard replacement beyond what the analyst UI already provides.
- Response handlers **default** to DB-state-only behavior. Real OS/network side-effects are opt-in per host via `WAZUH_AR_ENABLED` (Phase 11). With the flag off, `quarantine_host_lab` and `kill_process_lab` still write their DB markers + audit logs; they just don't touch iptables or kill anything. This is deliberate — demos, tests, and most development work should never need to spin up the full Wazuh stack. See ADR-0005 (handler shape) and ADR-0007 (AR dispatch).
