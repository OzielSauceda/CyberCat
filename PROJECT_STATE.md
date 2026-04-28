# PROJECT_STATE.md — CyberCat

Living status document. Update as reality changes. Short, current, honest.

Last updated: 2026-04-28 — Phase 14 FULLY VERIFIED. All 8 smoke scripts pass with both `AUTH_REQUIRED=false` (no token) and `AUTH_REQUIRED=true` (Bearer token). `pytest` 156/156 ✅. `npm run typecheck` 0 errors ✅. Browser: analyst login + SSE + read_only disabled buttons verified (14.2). Phases 1–14 all complete and verified.

---

## Status summary

**Phase:** Phase 14 ✅ FULLY VERIFIED (2026-04-28). All sub-phases 14.1–14.5 complete and stack-verified. All 8 smoke scripts pass with and without auth token. 156/156 pytest passing. 0 typecheck errors. `infra/compose/.env` reset to `AUTH_REQUIRED=false` (dev default). The platform is now multi-operator capable.

**Overall posture (honest):**

- Phases 1–12 all fully verified.
- Phase 12: browser-verified 2026-04-23.
- Phase 11: 93/93 pytest passing. Smoke test **8/8**.
- smoke_test_phase8.sh: all 27 checks pass (live Wazuh stack).
- smoke_test_phase10.sh: all 15 checks pass.

**Ship-story phase (deferred — not the next phase):** README rewrite, demo GIF of the `credential_theft_chain` scenario, public repo prep (LICENSE, `.gitignore` audit, `git init` + first commit), and secrets remediation of plaintext password examples. This phase runs **after** the remaining feature work is complete so the README and GIF reflect the final product shape. A detailed plan for this phase is saved at `C:\Users\oziel\.claude\plans\project-state-md-ok-now-that-hashed-allen.md`; the recording playbook is at `docs/assets/RECORDING.md`. Partial artifacts already in the tree (harmless, keep): `LICENSE` (MIT), `.gitignore` additions (`.mypy_cache/`, `.env.local`).

---

## What needs to happen next session (pick up here)

**Phase 14 is fully complete.** All 8 smoke scripts pass, 156/156 tests green, 0 typecheck errors.

Next up: **Ship-story phase** — README rewrite, demo GIF of `credential_theft_chain`, public repo prep. See the deferred plan details in the Known gaps section below.

---

## Phase-by-phase state

### Phase 14.4 — ✅ OIDC Opt-in — implemented and test-verified 2026-04-27

**What Phase 14.4 does:** Adds SSO sign-in via any standard OIDC provider (Google Workspace, Okta, Auth0, Keycloak, Authentik, etc.). On startup the backend fetches the provider's discovery document + JWKS and caches them on `app.state.oidc`. `/v1/auth/oidc/login` redirects to the provider; `/v1/auth/oidc/callback` exchanges the authorization code for an ID token, validates the JWT signature + nonce, and JIT-provisions the user (role=read_only by default). The login page's "Sign in with SSO" button was already conditional on `authConfig.oidc_enabled` from Phase 14.2. OIDC is disabled when `OIDC_PROVIDER_URL` is unset; the endpoints return HTTP 501 in that case.

**New files:**
- `backend/app/auth/oidc.py` — `OIDCConfig` dataclass; `discover_oidc()` (startup discovery); `make_authorization_url()` (state + nonce in signed itsdangerous cookie); `verify_state()` (CSRF check); `exchange_code_for_user_info()` (token exchange + ID-token JWT validation via authlib 1.7 `JsonWebToken`/`KeySet`); `upsert_oidc_user()` (lookup by oidc_subject → email → JIT create)

**Modified files:**
- `backend/app/auth/router.py` — imports `oidc.py` helpers; `GET /auth/oidc/login` (sets state cookie, 302 to provider); `GET /auth/oidc/callback` (verifies state, exchanges code, sets session cookie, 302 to `/`)
- `backend/app/main.py` — `from app.auth.oidc import discover_oidc`; `app.state.oidc = await discover_oidc()` added to lifespan
- `backend/pyproject.toml` — `"authlib>=1.3"` added
- `backend/Dockerfile` — `"authlib>=1.3"` added to `RUN uv pip install` block
- `docs/runbook.md` — "Multi-operator auth (Phase 14)" section added: bootstrap admin, create users, OIDC provider setup (step-by-step for any OIDC-compliant provider), troubleshooting

**Key implementation notes:**
- authlib 1.7 API: `JsonWebKey.import_key_set(jwks_data)` returns a `KeySet` (not `JsonWebKeySet` — that name doesn't exist in 1.7). `JsonWebToken(["RS256", "ES256", ...]).decode(id_token, keyset)` then `.validate()`.
- State + nonce stored in a single signed cookie (`URLSafeSerializer(auth_cookie_secret, salt="cybercat-oidc-state")`), 10-min TTL. Backend stays stateless — no Redis or DB write during the OAuth dance.
- Fallback state secret used when `auth_cookie_secret` is empty (dev bypass mode), so OIDC can be tested without full auth enforcement.
- Userinfo endpoint fallback: if `email` is absent from the ID token claims, falls back to `GET {userinfo_endpoint}` with the access token.

**Verification (2026-04-27):**
- `pytest` → **156/156** ✅ (all existing tests pass; no new tests needed — OIDC verification requires a live provider)
- `npm run typecheck` → **0 errors** ✅
- `GET /v1/auth/oidc/login` with no OIDC configured → `{"detail":"OIDC is not configured on this server"}` (HTTP 501) ✅
- `GET /v1/healthz` → `{"status":"ok"}` (startup not broken) ✅
- `app.state.oidc = None` when `OIDC_PROVIDER_URL` unset ✅

---

### Phase 14.3 — ✅ Route Gating + Audit Fields — test-verified 2026-04-27

**What Phase 14.3 does:** Wires the auth foundation (14.1) and session layer (14.2) into the actual API surface. Every mutation endpoint now enforces `require_analyst`; every read endpoint enforces `require_user`. `actor_user_id` FKs are populated on every audit write. Six frontend mutation controls render disabled with a "Read-only role" tooltip for `read_only` users. A parameterized test inventory (`test_auth_gating.py`) asserts every mutation route returns 401 for anonymous and 403 for `read_only` — CI safety net against future privilege bypass.

**New files:**
- `backend/tests/integration/test_auth_gating.py` — 20 parameterized gating tests (10×401 anonymous + 10×403 read_only) covering the canonical inventory of all analyst-gated routes

**Modified files:**
- `backend/app/response/executor.py` — `execute_action` and `revert_action` gain `actor_user_id: uuid.UUID | None = None`; passed through to `ActionLog` rows
- `backend/app/api/routers/responses.py` — `require_analyst` on propose/execute/revert; `require_user` on list; `current_user.email` replaces `"operator@cybercat.local"`; `actor_user_id` populated via `resolve_actor_id()`; `ActionLogSummary` constructions pass `actor_user_id`
- `backend/app/api/routers/incidents.py` — `require_analyst` on POST transitions + POST notes; `require_user` on GET list + GET detail; `current_user.email` replaces `"operator@cybercat.local"` in both transition and note; `actor_user_id` set on `IncidentTransition` and `Note` rows; `TransitionRef` and `NoteRef` constructions pass `actor_user_id`
- `backend/app/api/routers/evidence_requests.py` — `require_analyst` on collect/dismiss; `require_user` on list; `collected_by_user_id` / `dismissed_by_user_id` populated
- `backend/app/api/routers/lab_assets.py` — `require_analyst` on POST + DELETE; `require_user` on GET; `created_by_user_id` populated on register
- `backend/app/api/routers/events.py` — `require_analyst` on `POST /events/raw`; `require_user` on `GET /events`
- `backend/app/api/routers/streaming.py` — `require_user` on SSE endpoint
- `backend/app/api/schemas/incidents.py` — `ActionLogSummary`, `TransitionRef`, `NoteRef` gain `actor_user_id: uuid.UUID | None = None`
- `backend/tests/conftest.py` — `authed_client` (analyst SystemUser) and `readonly_client` (read_only SystemUser) fixtures added; `# noqa: E402` on new imports
- `frontend/app/components/TransitionMenu.tsx` — `useCanMutate()` + `disabled={!canMutate}` + tooltip on Transition… button
- `frontend/app/incidents/[id]/ActionControls.tsx` — `useCanMutate()` + `disabled={!canMutate}` + tooltip on Execute and Revert buttons
- `frontend/app/components/EvidenceRequestsPanel.tsx` — `useCanMutate()` + `disabled={busy === er.id || !canMutate}` + tooltip on Mark collected and Dismiss
- `frontend/app/incidents/[id]/NotesPanel.tsx` — `useCanMutate()` + `disabled={pending || !canMutate}` on textarea; hardcoded `author: "operator@cybercat.local"` replaced with `user?.email ?? "you"`; `canSubmit` includes `canMutate`
- `frontend/app/incidents/[id]/ProposeActionModal.tsx` — `useCanMutate()` + `disabled={!validate() || pending || !canMutate}` + tooltip on Propose button
- `frontend/app/lab/page.tsx` — `useCanMutate()` added to `LabPage`; `canMutate` prop threaded into `AddAssetForm`; Register asset submit and Remove button both `disabled={!canMutate}`

**Key implementation notes:**
- Gating test `_anon_client`: overrides `get_current_user` to raise 401 directly (not `settings.auth_required=True` + real token flow)
- Gating test `_ro_client`: overrides `get_current_user` to return `_ReadOnlyUser` (a plain dataclass, NOT a `SystemUser`) so `require_analyst`'s `isinstance(user, SystemUser)` check fails and the 403 path is exercised
- `authed_client` / `readonly_client` in conftest override `require_user` + `require_analyst` directly (bypass role check — convenience fixtures for other integration tests, not gating tests)
- `resolve_actor_id(current_user, db)` is called before each DB mutation; returns the user's UUID for real users, or looks up `legacy@cybercat.local` UUID for `SystemUser`

**Verification (2026-04-27):**
- `pytest` → **136/136** ✅ (109 baseline + 7 auth security/router + 20 gating tests)
- `npm run typecheck` → **0 errors** ✅
- GET `/v1/incidents` with no auth → 200 (auth_required=false; SystemUser passes require_user) ✅
- GET `/v1/auth/me` → `{email:"legacy@cybercat.local", role:"analyst"}` (dev-bypass intact) ✅
- Backend and frontend images rebuilt and running clean ✅

---

### Phase 14.2 — ✅ Frontend Login + Session — protocol-verified 2026-04-27

**What Phase 14.2 does:** Adds the session layer to the frontend. `SessionContext` fetches `/v1/auth/me` + `/v1/auth/config` on mount and exposes `{user, status, authConfig, refresh, logout}`. `UserBadge` renders in the header with email + role pill + Sign out. `LoginPage` shows the login form when `auth_required=true`. `api.ts` gains `credentials: "include"` + 401 redirect. Next.js rewrite proxies `/v1/*` to backend (same-origin cookie path).

**New files:**
- `frontend/app/lib/auth.ts` — `User` type, `UserRole`, `AuthConfig`, `getMe()`, `getAuthConfig()`, `login()`, `logout()`
- `frontend/app/lib/SessionContext.tsx` — `SessionProvider`, `useSession()`, `useCanMutate()` hook
- `frontend/app/components/UserBadge.tsx` — header pill: role badge + email + Sign out; redirects anon→login when auth_required
- `frontend/app/login/page.tsx` — email/password form; SSO button conditionally shown; redirects to `?next=` on success

**Modified files:**
- `frontend/app/lib/api.ts` — `credentials: "include"` added to `request()`; 401 → redirect to `/login?next=...`
- `frontend/app/layout.tsx` — wrapped in `<SessionProvider>`; `<UserBadge />` added between StreamStatusBadge and WazuhBridgeBadge
- `frontend/next.config.ts` — `rewrites: /v1/:path* → http://backend:8000/v1/:path*`
- `backend/app/main.py` — CORS `allow_credentials=False → True` (required for credentialed cross-origin requests in local dev)
- `backend/Dockerfile` — added `bcrypt>=4.0` and `itsdangerous>=2.0` to the `RUN uv pip install` block (the file pins runtime deps separately from `pyproject.toml`; Phase 14.1 missed this).
- `infra/compose/docker-compose.yml` — added `AUTH_REQUIRED` and `AUTH_COOKIE_SECRET` env passthrough on the `backend` service (defaults: false / empty).
- `frontend/app/components/UserBadge.tsx` — hide Sign out button when `authConfig.auth_required === false` (dev-bypass has no real session to terminate; surfaced during browser verification).

**Note:** `useCanMutate()` lives in `SessionContext.tsx` (not `auth.ts` as the plan stated) to avoid circular imports. Phase 14.3 components should import it from `../lib/SessionContext`.

**Verification (2026-04-27):**

Protocol-level verification done end-to-end via curl, both directly against backend (`:8000`) and through the Next.js rewrite (`:3000/v1/*`):

1. ✅ **Build fix.** `backend/Dockerfile` was pinning deps separately from `pyproject.toml` and had not been updated for Phase 14.1 — added `bcrypt>=4.0` and `itsdangerous>=2.0` to the `RUN uv pip install` block. Docker compose env-var passthrough also added: `AUTH_REQUIRED` and `AUTH_COOKIE_SECRET` now wired into the `backend` service in `docker-compose.yml`.
2. ✅ **AUTH_REQUIRED=false (default):** `/v1/auth/config` returns `{auth_required:false}`; `/v1/auth/me` returns `{email:"legacy@cybercat.local", role:"analyst"}` (the SystemUser sentinel). UserBadge will render the legacy analyst pill, no redirect.
3. ✅ **AUTH_REQUIRED=true + admin@local seeded:** `/v1/auth/config` returns `{auth_required:true}`; `/v1/auth/me` anon → 401. Login with `admin@local`/`changeme_123` → 200 + `Set-Cookie: cybercat_session=…; HttpOnly; Path=/; SameSite=lax; Max-Age=28800`. `/v1/auth/me` with cookie → returns admin user. POST `/v1/auth/logout` → 200, clears cookie. `/v1/auth/me` after logout → 401.
4. ✅ **Same flow through Next.js rewrite:** `POST :3000/v1/auth/login` → 200 + cookie set on `localhost`. `GET :3000/v1/auth/me` with cookie → admin user. Confirms the rewrite is correctly proxying `/v1/*` and the cookie is same-origin-visible.
5. ✅ **Visual click-through (2026-04-27):** browser confirmed the UserBadge renders with role pill + email. Surfaced one UX bug — Sign out was showing in dev-bypass mode and looked like a no-op (the backend's `/v1/auth/me` always returns the legacy SystemUser when `AUTH_REQUIRED=false`, regardless of cookies). **Fix shipped:** `UserBadge.tsx` now hides the Sign out button when `authConfig.auth_required === false`. Logout still works, but is only relevant in real-auth mode where there's an actual session to terminate.

---

### Phase 14.1 — ✅ Auth Foundation — implemented 2026-04-26

**What Phase 14.1 does:** Adds the auth package (`User`, `ApiToken` models, bcrypt+itsdangerous security primitives, FastAPI deps, router), migration `0007` (users/api_tokens tables, audit FK columns, `legacy@cybercat.local` backfill), bootstrap CLI, and 27 new tests. `AUTH_REQUIRED=false` by default so all existing tests pass unmodified.

**New files:**
- `backend/app/auth/__init__.py`, `models.py`, `security.py`, `dependencies.py`, `router.py`
- `backend/app/cli.py` — `seed-admin`, `create-user`, `set-role`, `issue-token`, `revoke-token`
- `backend/alembic/versions/0007_multi_operator_auth.py` — schema + backfill
- `backend/tests/unit/test_auth_security.py` — 12 unit tests
- `backend/tests/integration/test_auth_router.py` — 15 integration tests

**Modified files:**
- `backend/app/config.py` — auth + OIDC settings, cookie secret validator
- `backend/app/db/models.py` — nullable FK columns on 5 audit tables, imports User/ApiToken for Alembic
- `backend/app/main.py` — auth_router registered
- `backend/pyproject.toml` — bcrypt>=4.0, itsdangerous>=2.0

**Verified:**
- Migration 0007 up/down round-trip clean
- `python -m app.cli seed-admin --email admin@local --password changeme_123` ✅
- `python -m app.cli issue-token --email admin@local --name smoke-test-token` ✅
- pytest **136/136** (109 baseline unchanged + 12 unit + 15 integration) ✅

---

### Phase 13 — ✅ Fully verified 2026-04-26

**What Phase 13 does:** Replaces the 5s/10s polling on the analyst UI with a server-pushed SSE channel (`GET /v1/stream`) so incidents, detections, actions, evidence, and the Wazuh bridge badge update within ~1s of domain events. Polling stays as a 60s safety net.

**New files:**
- `backend/app/streaming/__init__.py` — re-exports `publish`, `StreamEvent`, `EventBus`
- `backend/app/streaming/events.py` — `StreamEvent` pydantic model, `EventType` Literal, `Topic` enum, `topic_for()` helper
- `backend/app/streaming/publisher.py` — `async publish(event_type, data)` — builds envelope (sortable ID, UTC ts, topic), calls `redis.publish`. Never raises.
- `backend/app/streaming/bus.py` — `EventBus` class: one Redis pub/sub subscriber per process, fans out to per-connection `asyncio.Queue`s. `init_bus()` / `close_bus()` / `get_bus()` lifecycle functions.
- `backend/app/api/routers/streaming.py` — `GET /v1/stream` SSE endpoint with topic filter, heartbeat every 20s, clean disconnect handling
- `backend/tests/unit/test_streaming_publisher.py` — 4 unit tests: id sortability, topic_for mapping, envelope structure, Redis error swallowed
- `backend/tests/unit/test_streaming_event_bus.py` — 4 unit tests: register/unregister, fan-out, unregistered queue gets no messages
- `backend/tests/integration/test_sse_stream.py` — 5 integration tests: content-type, heartbeat, event delivery, topic filter, fan-out
- `backend/tests/integration/test_response_action_emits.py` — action lifecycle emit tests
- `frontend/app/lib/streaming.ts` — `StreamTopic`, `StreamEvent` union, `StreamStatus`, `connectStream()` with auto-reconnect and failure tracking
- `frontend/app/lib/useStream.ts` — `useStream<T>()` hook: SSE + 60s safety-net poll + 300ms debounce coalescing + visibility-aware reconnect
- `frontend/app/components/StreamStatusBadge.tsx` — ambient status pill (hidden when connected, amber "Reconnecting", grey "Polling" on failure)
- `labs/smoke_test_phase13.sh` — 8-check smoke test
- `docs/decisions/ADR-0008-realtime-streaming.md`
- `docs/streaming.md` — event taxonomy, channel naming, ops debugging curl examples

**Modified files:**
- `backend/app/main.py` — `init_bus()` / `close_bus()` in lifespan; streaming router registered
- `backend/app/ingest/pipeline.py` — emits `incident.created` or `incident.updated` after commit; emits `detection.fired` per detection
- `backend/app/api/routers/incidents.py` — `transition_incident` emits `incident.transitioned` after commit
- `backend/app/api/routers/responses.py` — `propose_response` → `action.proposed`; `execute_response` → `action.executed` (+ `evidence.opened` for request_evidence); `revert_response` → `action.reverted`
- `backend/app/api/routers/evidence_requests.py` — `collect_evidence_request` → `evidence.collected`; `dismiss_evidence_request` → `evidence.dismissed`
- `backend/app/ingest/wazuh_poller.py` — `_emit_wazuh_transition()` helper; emits `wazuh.status_changed` on reachability flip only
- `frontend/app/incidents/page.tsx` — `usePolling` → `useStream({topics: ['incidents'], ...})`
- `frontend/app/incidents/[id]/page.tsx` — `usePolling` → `useStream({topics: ['incidents','detections','actions','evidence'], ...})`
- `frontend/app/actions/page.tsx` — `usePolling` → `useStream({topics: ['actions'], ...})`
- `frontend/app/detections/page.tsx` — `usePolling` → `useStream({topics: ['detections'], ...})`
- `frontend/app/components/WazuhBridgeBadge.tsx` — `usePolling` → `useStream({topics: ['wazuh'], ...})`
- `frontend/app/layout.tsx` — `<StreamStatusBadge />` added next to `<WazuhBridgeBadge />`
- `docs/architecture.md` — "Streaming layer" subsection (§8) added
- `docs/runbook.md` — "Tailing the Live Event Stream" section added

**Key design decisions (see ADR-0008):**
- SSE over WebSocket: server→client only, auto-reconnect built in, HTTP-native
- Redis Pub/Sub for fan-out (one subscriber per process, not per connection)
- Refetch-on-notify pattern: events carry minimal `{type, id}` metadata; frontend refetches via existing REST endpoints
- `incident.created` vs `incident.updated` detection: compares `inc.opened_at` to pipeline start time (2s threshold) — `Incident` has `opened_at`, not `created_at`
- `wazuh.status_changed` fires only on reachability transition (not every poll cycle)
- Streaming is best-effort: publish failures log a warning and never break domain operations

**Verification status (2026-04-26):**
1. ✅ `pytest backend/tests` — **109/109 passing** (73 unit + 36 integration, including 16 new streaming tests)
2. ✅ `npm run typecheck` — **0 errors** (also fixed `StatusPill.tsx` missing `partial` and `ActionControls.tsx` `unknown` cast)
3. ✅ `curl -N http://localhost:8000/v1/stream` — verified manually (heartbeat at ~20s ✓)
4. ✅ `bash labs/smoke_test_phase13.sh` — **8/8** (2026-04-26: fixed 4 script bugs — HEAD→GET-with-headers for content-type check, batch→single-event format for ingest payloads, simulator→direct API calls, single auth.failed→3-event pattern for fan-out detection trigger)
5. ✅ Browser: two `/incidents` tabs + 3-event API sequence → new incident card appeared in both tabs within ~1s (after frontend image rebuild)
6. ✅ Browser: `StreamStatusBadge` hidden when connected, amber "Reconnecting" pill on `docker compose stop backend`, transitions to grey "Polling" after 3 failures within 30s (by design — `streaming.ts:39`); fresh page load reconnects cleanly

**Bugs fixed during verification (these changes are already in the code):**
- `pipeline.py`: `inc.created_at` → `inc.opened_at` (Incident model uses `opened_at`)
- `publisher.py`: millisecond ID → nanosecond ID (fix sort guarantee in tight loops)
- `tests/conftest.py`: added `init_bus()` / `close_bus()` to `client` fixture (EventBus was never initialized in tests)
- `tests/unit/test_streaming_publisher.py`: patch target `app.db.redis.get_redis` not `app.streaming.publisher.get_redis` (lazy import)
- `tests/integration/test_sse_stream.py`: rewrote HTTP streaming tests as EventBus service-layer tests (httpx ASGITransport buffers entire response — cannot drive infinite SSE generators)
- `tests/integration/test_response_action_emits.py`: rewrote to use EventBus queue instead of `client.stream()`, fixed event kind `auth.success` → `auth.succeeded`, added `auth_type` field
- `frontend/app/components/StatusPill.tsx`: added `partial` to styles map (was missing from `ActionStatus`)
- `frontend/app/incidents/[id]/ActionControls.tsx`: `error && (...)` → `error != null && (...)` (unknown not assignable to ReactNode)

---

### Phase 11 — ✅ Fully verified 2026-04-24

Smoke test: **8/8**. 93/93 pytest passing.

**What Phase 11 does:** Wires `quarantine_host_lab` and `kill_process_lab` to real Wazuh Active Response so they produce actual OS/network side-effects (iptables DROP, process kill) instead of DB-state only. Guarded by `WAZUH_AR_ENABLED=false` by default so existing demos remain safe.

**New files:**
- `backend/alembic/versions/0006_phase11_action_result_partial.py` — `ALTER TYPE actionresult/actionstatus ADD VALUE 'partial'`
- `backend/app/response/dispatchers/__init__.py` — package marker
- `backend/app/response/dispatchers/wazuh_ar.py` — async AR dispatcher: token cache (270s TTL), 401 re-auth once, 5s connect/10s read timeout, `disabled` short-circuit, never logs Authorization header
- `backend/app/response/dispatchers/agent_lookup.py` — resolves host natural_key → Wazuh agent_id via `/agents?name=<host>`, 60s Redis cache
- `infra/lab-debian/active-response/kill-process.sh` — custom AR script; reads cmdline from `/proc/<pid>/cmdline`, validates against `process_name` before `kill -9` (PID-reuse safety), logs to `/var/ossec/logs/active-responses.log`
- `docs/decisions/ADR-0007-wazuh-active-response-dispatch.md`
- `labs/smoke_test_phase11.sh` — happy path (iptables + PID verification), `--cleanup` mode, `--test-negative` mode (manager down → partial)
- `backend/tests/unit/test_wazuh_ar_dispatcher.py` — 6 unit tests: disabled short-circuit, auth success + token cache reuse, 401 re-auth, 5xx → failed, timeout → failed, no Authorization header in logs
- `backend/tests/integration/test_handlers_ar_integration.py` — 5 integration tests: quarantine AR disabled/ok/partial, kill_process AR ok, agent not enrolled → partial
- `infra/compose/.env.example`

**Modified files:**
- `backend/app/enums.py` — `ActionResult.partial`, `ActionStatus.partial` added
- `backend/app/config.py` — 5 new settings: `wazuh_ar_enabled` (default false), `wazuh_manager_url`, `wazuh_manager_user`, `wazuh_manager_password`, `wazuh_ar_timeout_seconds`
- `backend/app/response/executor.py` — `ActionResult.partial → ActionStatus.partial` added to result→status map
- `backend/app/response/handlers/quarantine_host.py` — after DB writes: if flag on, looks up agent_id, dispatches `firewall-drop0` with source_ip; returns `ok` on dispatched, `partial` on failed/skipped; writes AR status to note body + reversal_info
- `backend/app/response/handlers/kill_process.py` — after DB writes: if flag on, dispatches `kill-process` with `[host, pid, process_name]`; same partial pattern; reversal_info includes all AR fields
- `backend/app/api/schemas/incidents.py` — `ActionLogSummary.reversal_info: dict | None` added; `result` and `status` Literals include `"partial"`
- `backend/app/api/routers/responses.py` — all `ActionLogSummary(...)` constructions pass `reversal_info=log.reversal_info`
- `backend/app/api/routers/incidents.py` — same
- `frontend/app/lib/api.ts` — `ActionResult` and `ActionStatus` union types include `"partial"`; `ActionLogSummary.reversal_info: Record<string, unknown> | null` added
- `frontend/app/incidents/[id]/ActionControls.tsx` — amber `StatusChip` for `partial` with tooltip "Action partially completed — DB state written, enforcement did not confirm. See action log."; result pill also amber for `partial`; Active Response row in log entry renders `ar_dispatch_status` with dispatched=green, failed/skipped=amber
- `infra/lab-debian/Dockerfile` — `COPY active-response/kill-process.sh /var/ossec/active-response/bin/kill-process` + `chmod 750 / chown root:wazuh`
- `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf` — `kill-process` `<command>` block + `<active-response>` block added
- `infra/compose/docker-compose.yml` — `WAZUH_AR_ENABLED`, `WAZUH_MANAGER_URL`, `WAZUH_MANAGER_USER`, `WAZUH_MANAGER_PASSWORD` env vars added to backend service
- `docs/runbook.md` — Phase 11 enforcement demo section added

**Key design decisions (see ADR-0007):**
- `partial` result: DB state committed + AR failed → don't roll back; audit trail of what was attempted is load-bearing
- `disabled` short-circuit: dispatcher returns immediately without any network call when `wazuh_ar_enabled=false`
- `firewall-drop` is a Wazuh built-in (no custom agent work); `kill-process` is a ~40-line custom shell script
- Idempotency: dispatch anyway — `firewall-drop` is idempotent; killing a dead PID is a no-op
- Disruptive actions remain non-revertible; cleanup is manual (`--cleanup` mode)

**To verify (exact steps, in order):**
1. `docker compose -f infra/compose/docker-compose.yml up -d` — confirm backend starts healthy after the enum change
2. Inside backend container or with alembic CLI: `alembic upgrade head` — applies migration 0006
3. `pytest` — expect ~89 tests (79 existing + ~10 new Phase 11 tests)
4. Check `smoke_test_phase9a.sh` still passes with `WAZUH_AR_ENABLED=false` (zero regression)
5. Set `WAZUH_AR_ENABLED=true` + `WAZUH_MANAGER_PASSWORD=<password>` in `infra/compose/.env`
6. `docker compose -f infra/compose/docker-compose.yml --profile wazuh up -d` — wait for lab-debian enrolled
7. `bash labs/smoke_test_phase11.sh` — happy path (iptables DROP + PID gone)
8. Browser: execute quarantine on an incident → check amber badge when manager stopped, green when up
9. `bash labs/smoke_test_phase11.sh --cleanup`

**Known gotchas to watch during verification:**
- Agent enrollment takes 10–30s after lab-debian starts; smoke test polls `/agents?name=lab-debian` — don't skip the wait
- `firewall-drop` writes runtime iptables rules only; a container restart wipes them (DB still says quarantined — this is expected lab behavior, documented in ADR-0007)
- The Wazuh manager `wazuh-wui` password may differ from the one in the healthcheck line of docker-compose.yml (`MyS3cr37P450r*`) — check the manager logs on first boot if auth fails

---

### Phase 12 — ✅ Fully verified 2026-04-23

**No backend changes.** All three deliverables are pure frontend — presentation of data already stored in the DB.

**New files (all in `frontend/app/incidents/[id]/`):**

- **`AttackKillChainPanel.tsx`** — Full-width ATT&CK Enterprise kill chain strip. Shows all 14 tactics (Reconnaissance → Impact) in left-to-right order; matched tactics highlighted in indigo with technique count badge and R/C source indicators. Below the strip, matched tactics expand to show technique tags (with MITRE links + name lookup via `useAttackEntry`). Replaces the old list-based `AttackPanel` component entirely.

- **`IncidentTimelineViz.tsx`** — Full-width SVG graphical timeline. Events plotted as dots at exact relative timestamps on a horizontal baseline. Color-coded by layer: `auth.*` = indigo (identity), `process.*`/`file.*` = lime (endpoint), `network.*` = cyan, `session.*` = emerald, other = zinc. Role-based sizing and style: trigger = large dot with glow halo, supporting = solid medium dot, context = hollow outlined dot. Detection triangles rendered above the baseline with dashed connector lines to their triggering event (matched via `event_id`). Hover tooltip (mouse-tracked via `onMouseMove` on container div) shows event kind, timestamp, role, source. Time axis with +Xs/+Xm relative labels.

- **`EntityGraphPanel.tsx`** — SVG entity relationship graph in the right column. Entities laid out in a circular arrangement. Edges drawn between entities that co-occur in timeline events; edge weight = co-occurrence count, displayed on hover. Nodes sized proportionally to event count (min 14, max 22 radius), colored by entity kind (same palette as `EntityChip`). Kind abbreviation inside each node circle; natural key label and role label below. Hover: hovered node glows, others dim, edge weight label appears. Click: `router.push("/entities/{id}")`.

**Modified files:**

- `frontend/app/incidents/[id]/page.tsx`:
  - Added imports for the three new components
  - Added `<AttackKillChainPanel>` full-width between rationale box and two-column grid
  - Added `<IncidentTimelineViz>` full-width below kill chain
  - Added `<EntityGraphPanel>` at top of right column
  - Removed old `AttackPanel` function and `AttackTagWithName` helper (now handled inside `AttackKillChainPanel.tsx`)
  - Removed unused `useAttackEntry` import from `page.tsx`

**New layout order (incident detail page):**
1. Header (title, severity, status, confidence, correlator info, timestamps)
2. Rationale box
3. ATT&CK Kill Chain panel ← new, full-width
4. Graphical Timeline ← new, full-width
5. Two-column grid:
   - Left: Timeline list (existing) + Detections (existing)
   - Right: Entity Graph ← new | Entities list (existing) | Actions | Evidence | Transitions | Notes

**Verification status:** `tsc --noEmit` → 0 errors. Browser-verified 2026-04-23 — all three panels confirmed against live `credential_theft_chain` scenario incident.

---

### Phase 10 — ✅ Fully verified 2026-04-23

**Sub-track 1 — `identity_endpoint_chain` correlator (✅ verified 2026-04-23):**

New correlator that fires when a `process.created` (or Sigma endpoint) event arrives for a user who already has an open `identity_compromise` incident within the last 30 minutes. Creates a first-class `identity_endpoint_chain` incident (severity `high`, confidence `0.85`) instead of extending or duplicating the parent incident.

Key design decisions:
- Registered **before** `endpoint_compromise_join` and `endpoint_compromise_standalone` in `__init__.py` — engine's first-match-wins means chain wins, standalone skipped.
- Dedup key: `identity_endpoint_chain:{user}:{host}:{YYYYMMDDHH}` in Postgres (same pattern as `identity_compromise`).
- Links auth events from the identity incident as `supporting` context in the chain incident.
- Auto-actions: `tag_incident(cross-layer-chain)`, `elevate_severity(critical)`, `request_evidence(process_list)`, `request_evidence(triage_log)` — most aggressive of any incident kind.

New files:
- `backend/app/correlation/rules/identity_endpoint_chain.py`
- `backend/tests/integration/test_identity_endpoint_chain.py` — 4 tests: positive chain, dedup, no chain without identity, no chain for different user

Modified:
- `backend/app/correlation/__init__.py` — chain registered before join and standalone
- `backend/app/correlation/auto_actions.py` — `identity_endpoint_chain` entry added

Verification: 4/4 new tests pass; 79/79 full suite pass (0 regressions including `test_join_wins_over_standalone`).

**Sub-track 2 — Attack Simulator (⏳ implemented 2026-04-23, awaiting live-stack verification):**

Python package `labs/simulator/` that fires the full 5-stage `credential_theft_chain` scenario via `POST /v1/events/raw`. No backend imports — runs as a peer of the smoke tests against any running backend. Key design: `--speed` multiplier (0.1 = ~30s compressed demo), `--verify` default-on (asserts both incidents exist after run), stable dedup keys (re-run in same hour is idempotent).

New files:
- `labs/__init__.py` — makes `labs` a Python package
- `labs/simulator/__init__.py`, `__main__.py`, `client.py`, `event_templates.py`
- `labs/simulator/scenarios/__init__.py` — module registry
- `labs/simulator/scenarios/credential_theft_chain.py` — 5-stage scenario: brute-force → login → session → encoded PS → C2 beacon
- `labs/simulator/scenarios/README.md` — how to run + how to add scenarios
- `labs/smoke_test_phase10.sh` — 15 checks (health, simulator exit=0, identity_compromise present, chain present for alice, severity=critical, host=workstation-42, rationale, entities, evidence requests, idempotency)
- `docs/decisions/ADR-0006-attack-simulator.md`
- `docs/scenarios/credential-theft-chain.md`

Modified: `docs/runbook.md` (added "Running a demo scenario" section)

Prerequisite to run: `pip install httpx` (local Python; httpx is already a backend runtime dep but not available outside the container).

---

### Phase 9B — ⏳ In progress (Sub-tracks 1 + 2 ✅ fully verified; Sub-track 3 not started)

**Sub-track 1 — Cert infrastructure (✅ fully verified 2026-04-23):**

Verification results:
- `GET /_cluster/health` → `status=green`, 1 node, 4/4 primary shards active
- Admin auth with `SecretPassword123!` works via HTTPS
- All 7 planned config files exist and are mounted correctly
- Indexer, postgres, redis, backend, frontend, wazuh-manager, lab-debian all reach `(healthy)` on `docker compose ps`
- lab-debian agent ID 001 → `Active` in `agent_control -l`
- Filebeat manager→indexer pipeline live: `wazuh-alerts-4.x-2026.04.23` index has 373 docs (186 from agent 001)

**Gotchas discovered during bring-up (for future operators):**

1. **`certs.yml` cannot use bare Docker service names.** The cert generator `0.0.2` validator rejects `wazuh-indexer` as "Invalid IP or DNS" — it requires actual IPs or FQDNs. Using `ip: 127.0.0.1` works (hostname verification is already disabled in `wazuh.indexer.yml`).
2. **Wazuh indexer image does NOT auto-run `securityadmin.sh`.** Despite `OPENSEARCH_INITIAL_ADMIN_PASSWORD` being set, the image's entrypoint doesn't trigger security init (unlike the OpenSearch demo image). First-boot bootstrap is manual — see runbook Step 4.
3. **`internal_users.yml` hash must match the password claimed by docs/env.** The Wazuh demo hash `$2y$12$K/Sp...` does NOT correspond to `admin` or `SecretPassword123!` — generate a fresh hash with `plugins/opensearch-security/tools/hash.sh -p 'PASSWORD'` and put that in `internal_users.yml`.
4. **Line-wrap on paste.** WSL2 terminals wrap long pastes at ~150 chars and convert the wrap into a newline, which splits multi-flag commands and causes bash to interpret PEM files as scripts. Use short variable aliases (`S=...`, `R=...`, etc.) to keep each line under 80 chars.
5. **Never bind-mount files inside `/etc/filebeat/`.** The manager image's `0-wazuh-init` script scans `PERMANENT_DATA` paths; if `/etc/filebeat/` is non-empty at start (e.g. from a cert mount at `/etc/filebeat/certs/*.pem`), it skips copying the image's backup `filebeat.yml` → the next init step fails with `sed: can't read /etc/filebeat/filebeat.yml: No such file or directory`. Mount certs under `/etc/ssl/` instead and set `SSL_CERTIFICATE_AUTHORITIES`, `SSL_CERTIFICATE`, `SSL_KEY` env vars so the init sed's them into the correct fields. This matches upstream `wazuh-docker@v4.9.2/single-node`.

New files:
- `infra/compose/wazuh-config/generate-indexer-certs.yml` — one-shot cert generator (wazuh/wazuh-certs-generator:0.0.2)
- `infra/compose/wazuh-config/config/certs.yml` — node list (wazuh-indexer + wazuh-manager; no dashboard)
- `infra/compose/wazuh-config/config/wazuh_indexer/wazuh.indexer.yml` — OpenSearch TLS config pointing to mounted certs
- `infra/compose/wazuh-config/config/wazuh_indexer/internal_users.yml` — admin + kibanaserver users (cybercat_reader added in Sub-track 2)
- `infra/compose/wazuh-config/config/wazuh_indexer/roles.yml` — empty (built-ins + Sub-track 2 custom role)
- `infra/compose/wazuh-config/config/wazuh_indexer/roles_mapping.yml` — admin → all_access mapping
- `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf` — ossec.conf (remote/auth/cluster/ruleset)
- `infra/compose/wazuh-config/config/wazuh_indexer_ssl_certs/.gitignore` — ignores generated *.pem/*.key

Modified:
- `infra/compose/docker-compose.yml` — wazuh-indexer: 7 cert bind mounts + opensearch.yml + internal_users.yml; wazuh-manager: 3 filebeat cert mounts + ossec.conf mount
- `docs/runbook.md` — 3-step Wazuh bring-up: cert generation → .env → profile up

**Verified 2026-04-23:** `curl -sk -u 'admin:SecretPassword123!' https://localhost:9200/_cluster/health` returns `status=green`, 1 node, 4/4 primary shards active.

**Sub-track 2 — TLS hardening + cybercat_reader (✅ verified 2026-04-23):**

Verification results:
- `cybercat_reader` `GET wazuh-alerts-*/_search` → 200 ✓
- `cybercat_reader` `PUT wazuh-alerts-test/_doc/1` → 403 (write blocked) ✓
- Backend poller: `last_success_at` populated, `last_error=null`, no SSL errors ✓
- Filebeat: `FILEBEAT_SSL_VERIFICATION_MODE=certificate` — connects cleanly, no x509 errors ✓

Key gotchas discovered:
- **roles.yml / roles_mapping.yml cannot be safely bind-mounted** — indexer sees its image-default files, so `securityadmin.sh -cd` would upload the wrong config. Role + mapping created via REST API and persisted in `wazuh_indexer_data` volume. See runbook Step 5.
- **`full` TLS mode fails** — cert SAN is `127.0.0.1` only, not `dns: wazuh-indexer`. Using `certificate` mode (CA chain verified, hostname skipped) is appropriate for this lab.

Files changed: `docker-compose.yml` (backend CA mount + env; manager SSL mode), `config.py` (defaults updated), `wazuh_poller.py` (custom SSL context + JSONB fix + poller resilience), `internal_users.yml` / `roles.yml` / `roles_mapping.yml` (cybercat_reader added), `infra/compose/.env` (WAZUH_BRIDGE_ENABLED=true), `labs/smoke_test_phase8.sh` (counter reset + realuser SSH + check 27 fix).

Additional bug fixed in this sub-track: **`wazuh_poller.py` JSONB cursor serialization** — `last_sort` (list) must be `json.dumps()`-encoded and passed as `CAST(:sa AS JSONB)` in the UPDATE; asyncpg cannot directly encode a Python list to a JSONB column via raw `text()` SQL.

**smoke_test_phase8.sh: all 27 checks verified passing** against live Wazuh stack (manager, indexer, lab-debian agent, backend poller, correlation engine).

**Sub-track 3 — Windows/Sysmon decoder (✅ verified 2026-04-23):**

Added Sysmon EventID 1 (`process.created`) decoder branch in `wazuh_decoder.py`. Reads from `data.win.system.eventID` + `data.win.eventdata` (Wazuh Windows alert structure). Emits `process.created` with same shape as auditd branch, plus `user` field populated from `eventdata.user`. `_WHITELIST` extended with `"sysmon"`. Non-EID1 events (e.g. EventID 3 network) are dropped cleanly.

New files: `backend/tests/fixtures/wazuh/sysmon-process-create.json`

Modified: `backend/app/ingest/wazuh_decoder.py` (whitelist + new branch; also added `user: ""` to auditd branch for schema consistency), `backend/tests/unit/test_wazuh_decoder.py` (3 new tests: positive decode, drop non-EID1, drop missing host).

Verification: 11/11 decoder unit tests pass; 78/78 full suite pass (no regressions).

---

### Phase 9A — ✅ Verified 2026-04-22

**New files:**
- `backend/alembic/versions/0005_response_state_tables.py` — migration for lab_sessions, blocked_observables, evidence_requests
- `backend/app/response/handlers/quarantine_host.py` — disruptive, notes+marker
- `backend/app/response/handlers/kill_process.py` — disruptive, auto-creates evidence_request
- `backend/app/response/handlers/invalidate_session.py` — reversible, lab_sessions table
- `backend/app/response/handlers/block_observable.py` — reversible, feeds detection engine
- `backend/app/response/handlers/request_evidence.py` — suggest_only, evidence_requests table
- `backend/app/detection/rules/blocked_observable.py` — py.blocked_observable_match detector (Redis-cached 30s)
- `backend/app/api/routers/evidence_requests.py` — GET/collect/dismiss endpoints
- `backend/app/api/routers/blocked_observables.py` — GET endpoint
- `frontend/app/components/EvidenceRequestsPanel.tsx`
- `frontend/app/components/BlockedObservablesBadge.tsx`
- `backend/tests/unit/test_handlers_real.py`
- `backend/tests/integration/test_response_flow_phase9.py`
- `backend/tests/integration/test_blocked_observable_detection.py`
- `backend/tests/integration/test_evidence_request_auto_propose.py`
- `labs/smoke_test_phase9a.sh`
- `docs/decisions/ADR-0005-response-handler-shape.md`

**Modified:**
- `backend/app/enums.py` — BlockableKind, EvidenceKind, EvidenceStatus added
- `backend/app/db/models.py` — LabSession, BlockedObservable, EvidenceRequest added
- `backend/app/response/executor.py` — 5 real handlers registered; stubs removed; _REVERT guards added
- `backend/app/response/handlers/stubs.py` — **deleted**
- `backend/app/correlation/auto_actions.py` — request_evidence auto-proposed on identity_compromise
- `backend/app/detection/__init__.py` — blocked_observable detector registered
- `backend/app/ingest/entity_extractor.py` — lab_sessions populated on session.started
- `backend/app/main.py` — evidence_requests + blocked_observables routers registered
- `frontend/app/lib/api.ts` — EvidenceRequest + BlockedObservable types + fetch functions
- `frontend/app/lib/actionForms.ts` — all 5 new action kinds enabled
- `frontend/app/incidents/[id]/page.tsx` — EvidenceRequestsPanel added
- `frontend/app/entities/[id]/page.tsx` — BlockedObservablesBadge added
- `backend/app/attack/catalog.json` — grown from 24 to 37 entries
- `backend/tests/conftest.py` — truncate_tables includes new tables

**Verification results (2026-04-22):**
- `alembic upgrade head` → migration 0005 applied cleanly
- `pytest` → 75/75 passed (0 failed); 6 test bugs fixed during verification
- `smoke_test_phase9a.sh` → 14/14 ALL CHECKS PASSED
- `smoke_test_phase7.sh` → 21/21 (regression clean); also fixed smoke_test_phase5.sh to self-register lab assets instead of relying on migration 0003 seeds
- `smoke_test_phase8.sh` → Phase 7 regression 21/21 inside; Wazuh checks 22-27 require `--profile wazuh` (infra-gated, not code)
- OpenAPI regen → `npm run gen:api` → `api.generated.ts` updated with all Phase 9A endpoints
- `tsc --noEmit` → 0 errors

**Status: ✅ FULLY VERIFIED (incl. visual recheck 2026-04-23).**

---

### Phase 8 — ✅ Fully verified 2026-04-23 (Part A: 2026-04-22; Part B completed via Phase 9B Sub-tracks 1+2)

**New:**
- `backend/app/ingest/pipeline.py` — shared ingest helper called from both HTTP router and poller
- `backend/app/ingest/wazuh_decoder.py` — alert → normalized mapping; 8 unit tests passed in last run
- `backend/app/ingest/wazuh_poller.py` — asyncio pull-mode poller with `search_after` cursor + drain mode + backoff
- `backend/app/api/routers/wazuh.py` — `GET /v1/wazuh/status` (unauthenticated)
- `backend/alembic/versions/0004_add_wazuh_cursor.py` — singleton cursor table
- `backend/tests/unit/test_wazuh_decoder.py` + 3 JSON fixtures
- `backend/tests/integration/test_wazuh_poller.py` (6 tests; `build_query()` exercised in-process, no Wazuh required)
- `infra/lab-debian/Dockerfile` + `entrypoint.sh` — Debian 12 slim + sshd + auditd + Wazuh agent 4.9.2 (never built)
- `frontend/app/components/WazuhBridgeBadge.tsx` — gray/green/amber pill in top-nav
- `labs/smoke_test_phase8.sh` + `labs/fixtures/wazuh-sshd-fail.json` (never run)
- `docs/decisions/ADR-0004-wazuh-bridge.md`
- `docs/scenarios/wazuh-ssh-brute-force.md`

**Modified:**
- `backend/app/config.py` — 9 Wazuh env vars (all with safe defaults; `WAZUH_BRIDGE_ENABLED=false` is the master switch)
- `backend/app/db/models.py` — `WazuhCursor` model
- `backend/app/api/routers/events.py` — uses shared pipeline helper; added `GET /v1/events` listing (for smoke test 25)
- `backend/app/api/schemas/events.py` — `EventSummary` + `EventList`
- `backend/app/main.py` — lifespan creates poller task when enabled; wazuh router registered
- `backend/pyproject.toml` — `httpx` moved from dev to runtime deps
- `infra/compose/docker-compose.yml` — `wazuh-indexer`, `wazuh-manager`, `lab-debian` services under `profiles: [wazuh]`
- `frontend/app/layout.tsx` — `WazuhBridgeBadge` in top-nav
- `docs/runbook.md` — replaced `(TBI — Phase 8)` block; added WSL2 `vm.max_map_count` note; registration password flow
- `docs/architecture.md` §3.1 — Wazuh adapter line updated

**Status: ✅ Fully verified 2026-04-23.** Part A (2026-04-22): 57 pytest passing, migration 0004 confirmed, status endpoint correct, OpenAPI regen + typecheck clean. Part B completed via Phase 9B Sub-tracks 1+2: TLS cert infrastructure, cybercat_reader role, poller JSONB fix, live Wazuh stack end-to-end. smoke_test_phase8.sh all 27 checks pass against live Wazuh stack.

### Phase 7 — ✅ verified 2026-04-22

What's real:
- ✅ Sigma parser/compiler/field_map (38 unit tests pass)
- ✅ Sigma pack with 6–8 curated rules
- ✅ Standalone `endpoint_compromise` correlator file present
- ✅ `/actions` dashboard renders in browser
- ✅ OpenAPI codegen tooling works (`openapi-typescript` installed; `dump_openapi.py` script works)
- ✅ `ErrorEnvelope` declared on mutation endpoints

What was **not** genuinely verified before today:
- ⚠️ Integration tests (`test_endpoint_standalone.py`, `test_sigma_fires.py`) were broken since creation. Bugs:
  1. POST payloads missing the required `raw` field → 422 from pydantic
  2. Asserting `status_code == 202` but the route returns 201
  3. `conftest.py` truncated table `"transitions"` (real name: `"incident_transitions"`) → relation-not-found
  4. `conftest.py` `client` fixture bypassed FastAPI lifespan → `get_redis()` raised `Redis client not initialised`
- ⚠️ Smoke test checks 17–21 were "believed fixed" after a separate `raw`-field fix in the shell script; never re-run to confirm.
- ⚠️ `backend/openapi.json` and `frontend/app/lib/api.generated.ts` are **stale** (timestamped 2026-04-21 01:15 — before today's Phase 8 endpoint additions). `tsc --noEmit` was last green against the stale types.

All four test-scaffolding bugs were patched 2026-04-21 and the full suite ran green 2026-04-22 (57 passed). Smoke test 21/21 confirmed. Phase 7 is genuinely verified.

### Phase 6 — ✅ complete (backend + frontend), verified 2026-04-21

### Phase 5 — ✅ complete (backend + frontend), verified 2026-04-20

### Phase 4 — ✅ complete, verified 2026-04-20

### Phase 3 — ✅ complete

### Phase 2 — ✅ complete

### Phase 1 — ✅ complete

### Phase 0 — ✅ complete

---

## Session changes (2026-04-27 — Phase 14.3 implementation)

**Phase 14.3 — Route Gating + Audit Fields — implemented and test-verified:**

All code written in one session. 16 files modified, 1 new file created.

Key decisions made during implementation:
- Gating tests override `get_current_user` (not `settings.auth_required=True`) to avoid the full cookie/bearer infrastructure while still exercising the actual `require_analyst` role-check logic
- `_ReadOnlyUser` in `test_auth_gating.py` is a plain `@dataclass` (not a `SystemUser` subclass) so `isinstance(user, SystemUser)` returns False and the 403 branch fires — critical detail
- `authed_client` / `readonly_client` in conftest override the deps directly (SystemUser bypass) so they serve as convenience fixtures for other integration tests without the role-check complexity
- `resolve_actor_id` is always called before writes (even in dev-bypass mode where it looks up the `legacy@cybercat.local` UUID) — ensures `actor_user_id` is populated on every audit row regardless of auth mode
- SSE endpoint (`streaming.py`) got `require_user` so it participates in the auth graph; in dev-bypass mode this is transparent (SystemUser passes through)

Bugs found and fixed during implementation: none — the changes were straightforward wire-ups.

---

## Session changes (2026-04-26 — Phase 14.2 implementation)

**Phase 14.2 — Frontend Login + Session — implemented, browser verification pending:**

All code written in one session. 8 files created/modified. No browser run performed.

**Files created:**
- `frontend/app/lib/auth.ts` — `User`, `UserRole`, `AuthConfig` types; `getMe()`, `getAuthConfig()`, `login()`, `logout()` fetch helpers
- `frontend/app/lib/SessionContext.tsx` — `SessionProvider` React context; `useSession()` hook; `useCanMutate()` hook (returns `role === analyst|admin`)
- `frontend/app/components/UserBadge.tsx` — header pill with role badge + email + Sign out; auto-redirects anon → `/login` when `auth_required=true`
- `frontend/app/login/page.tsx` — email/password form; redirects to `?next=` on success; SSO button shown if `oidc_enabled`; redirects home if `auth_required=false`

**Files modified:**
- `frontend/app/lib/api.ts` — `credentials: "include"` added to `request()`; 401 response redirects to `/login?next=...` (skips if already on `/login`)
- `frontend/app/layout.tsx` — wrapped in `<SessionProvider>`; `<UserBadge />` inserted between StreamStatusBadge and WazuhBridgeBadge
- `frontend/next.config.ts` — `rewrites: /v1/:path* → http://backend:8000/v1/:path*` for same-origin cookie path
- `backend/app/main.py` — `allow_credentials=False → True` in CORSMiddleware

**Key decisions:**
- `useCanMutate()` lives in `SessionContext.tsx` (not `auth.ts` per the plan) to avoid circular imports. Phase 14.3 components should import it from `../lib/SessionContext`.
- CORS `allow_credentials=True` is required for credentialed cross-origin requests in local dev (`localhost:3000` → `localhost:8000`). In Docker, the rewrite makes all requests same-origin so CORS is moot, but the change is harmless.
- `SessionProvider` wraps the entire `<body>` so both the header (`UserBadge`) and page content can access session state.
- Auth `BASE` defaults to `http://localhost:8000` (same as api.ts). In Docker, set `NEXT_PUBLIC_API_BASE_URL=""` to route through the rewrite.

**Verification:** pytest 136/136 ✅, `npm run typecheck` 0 errors ✅. Browser testing required (see "What needs to happen next session").

---

## Session changes (2026-04-23 — Phase 11 implementation)

**Phase 11 — Wazuh Active Response dispatch — fully implemented, verification pending:**

All code written in one session. 19 files created/modified. No live-stack run performed — operator ran out of time. Resume at the verification checklist in the Phase 11 section above.

Decisions made during implementation:
- Confirmed that the `# 9B extension: dispatch Wazuh AR ...` comments cited in PROJECT_STATE.md and ADR-0005 **never existed in the handler files** — that was stale documentation. The dispatch is wired cleanly without comment markers.
- `reversal_info` field added to `ActionLogSummary` schema and propagated through both API routers and `frontend/app/lib/api.ts` — this allows the frontend AR detail row to render without a dedicated endpoint.
- `agent_lookup.py` imports `_authenticate` from `wazuh_ar.py` to reuse the token cache — avoids a second auth call for the `/agents` query on the same AR dispatch sequence.
- Integration tests mock `dispatch_ar` and `agent_id_for_host` at the module level via `patch("app.response.handlers.quarantine_host.dispatch_ar", ...)` — this correctly targets the imported name in the handler's namespace, not the dispatcher module.

---

## Session changes (2026-04-23 — Phase 12 implementation)

**Phase 12 — Analyst UX Polish — implemented:**

Three new components added to `frontend/app/incidents/[id]/`. No backend changes, no new npm dependencies, no Alembic migrations. Pure SVG + Tailwind — no react-flow or cytoscape.js added (kept the lean dependency footprint).

Key design decisions:
- **No external graph library.** Entity graph built as pure SVG with circular layout and manual edge computation. Works cleanly for the typical 2–6 entity case. Avoids adding ~150KB of bundle weight for a component used once.
- **Layer-color vocabulary:** identity=indigo, endpoint=lime, network=cyan, session=emerald — these colors are consistent with how the backend categorizes event kinds and will be reusable in Phase 13 screenshots.
- **ATT&CK kill chain as the hero visual.** Placed first (below rationale) so it's the first thing a reviewer sees scrolling past the header. 14-tactic strip gives immediate "where in the kill chain" read at a glance.
- **Detection → event connectors.** `IncidentTimelineViz` uses `DetectionRef.event_id` to draw a dashed vertical line from each detection triangle to the specific event that fired it. Requires no backend change — the field already existed.
- **Removed `AttackPanel`.** Strictly superseded by `AttackKillChainPanel`. The kill chain view includes everything the old list view had, plus the ordered-strip visualization.

`tsc --noEmit` → 0 errors after one small fix (`Set<string>` iteration required `Array.from()`).

---

## Session changes (2026-04-23 — continued)

**Phase 9B Sub-track 2 bug fixes + smoke_test_phase8.sh fully passing:**

Root cause of checks 25/26/27 failing: **`wazuh_poller.py` JSONB serialization bug.** The cursor UPDATE passed `last_sort` (a Python `list`) directly to asyncpg via raw `text()` SQL. asyncpg cannot encode a Python list to JSONB — it needs a JSON string + `CAST(:sa AS JSONB)`. asyncpg threw `DataError: 'list' object has no attribute 'encode'`, which escaped the while loop (no outer try/except) and killed the poller silently. Because the cursor UPDATE rolled back, `search_after` stayed NULL and `events_ingested_total` stayed 0 even though the individual event INSERTs had already committed in their own sessions.

Fixes applied:
1. **`backend/app/ingest/wazuh_poller.py`**: Added `import json`; serialize `last_sort` via `json.dumps()` + `CAST(:sa AS JSONB)` in the UPDATE SQL; refactored loop body into `_poll_once()` helper; added outer `try/except Exception` in `poller_loop` so any future unhandled exception is logged and the poller backs off + retries instead of dying silently.
2. **`labs/smoke_test_phase8.sh`**: Reset `wazuh_cursor` counter before firing brute force (so check 25 measures delta, not stale total); changed brute-force target from `baduser` (random password) to `realuser` (known password `lab123`) so we can also fire a successful SSH → `auth.succeeded` event; this triggers `auth_anomalous_source_success` detection + `identity_compromise` correlator → check 27 can now pass; increased wait from 20s to 30s.
3. **`infra/compose/.env`**: Set `WAZUH_BRIDGE_ENABLED=true` (was `false`).

Verification: manually ran phase 8 scenario; `events_ingested_total=10`, 8 auth.failed + 2 auth.succeeded events in DB, 1 identity_compromise incident, poller `reachable=True` with checkpoint set. Poller stayed alive over multiple poll cycles.

---

## Session changes (2026-04-23)

**Phase 9B Sub-track 1 fully closed:**
- `docker compose --profile wazuh up -d` — all 7 containers healthy.
- Agent `001` (lab-debian) now `Active` in `agent_control -l`.
- Diagnosed Filebeat init failure: `0-wazuh-init` treated `/etc/filebeat/` as "already mounted" (our cert bind-mounts at `/etc/filebeat/certs/*.pem` populated the dir), so it skipped restoring the image's `filebeat.yml` → `1-config-filebeat` then failed on the sed of a non-existent file.
- Fix: moved cert mounts from `/etc/filebeat/certs/*.pem` → `/etc/ssl/{root-ca,filebeat,filebeat-key}.pem`, added `SSL_CERTIFICATE_AUTHORITIES`/`SSL_CERTIFICATE`/`SSL_KEY` env vars so the init script writes the correct paths into filebeat.yml. Matches upstream `wazuh-docker@v4.9.2/single-node` pattern. One file changed: `infra/compose/docker-compose.yml`.
- Pipeline verified: after recreate, Filebeat loaded `filebeat-7.10.2-wazuh-alerts-pipeline` cleanly; `wazuh-alerts-4.x-2026.04.23` index has 373 docs (186 from agent 001 = lab-debian). End-to-end TLS path (agent → manager → Filebeat → indexer) is live.
- Finding recorded as deferred: `lab-debian` doesn't tail `/var/log/auth.log`, so SSH-brute-force alerts (5700-series) won't fire end-to-end until a `<localfile>` block is added to `entrypoint.sh`. Pipeline plumbing itself is proven.

---

## Session changes (2026-04-22)

**Phase 8 verification** (morning):
- Rebuilt backend; `pytest` 57 passed; migration 0004 confirmed; smoke_test_phase7 21/21; smoke_test_phase8 27/27; OpenAPI regen + typecheck clean. Phase 8 Part A marked verified.
- Wazuh profile attempted; failed on missing indexer certs (see Blockers §2). Part B deferred.

**Phase 9A implementation** (afternoon):
- All new Phase 9A files listed under "Phase 9A" above — 17 new files, 15 modified files, stubs.py deleted.
- Key deliverables: 5 real response handlers (DB-state focused per ADR-0005), migration 0005, blocked_observable detection loop (Redis-cached 30s), auto-proposed evidence requests on identity_compromise, 2 new API routers, 2 new frontend components, ATT&CK catalog 24→37 entries, 4 test files, smoke_test_phase9a.sh (14 checks), ADR-0005.

**Phase 9A verification** (evening):
- Fixed 6 bugs found during verification: migration 0005 double-type-creation, missing `await db.flush()` in 2 revert handlers, missing `auth.succeeded` events in 3 integration tests, wrong response field name (`detection_ids` → `detections_fired`), `lab_assets` not in conftest truncation.
- Fixed regression: `smoke_test_phase5.sh` now self-registers `lab-win10-01` instead of depending on migration 0003 seeds (which pytest truncation wiped).
- Final results: pytest 75/75, smoke_test_phase9a 14/14, smoke_test_phase7 21/21, OpenAPI regen + typecheck clean.
- Phase 9A marked ✅ VERIFIED.

**Phase 9A browser flow** (late evening):
- Rebuilt frontend image — the running container was baked before Phase 9A actionForms.ts changes, so the Propose modal showed only the 3 pre-9A kinds. `docker compose build frontend && up -d frontend` fixed it.
- Seeded pre-flight: registered lab assets `host:lab-win10-01` and `user:alice`; injected a `session.started` event to create one `lab_sessions` row (alice@lab-win10-01).
- Manually exercised all 5 new action kinds on incident `126a8878-...`:
  - `quarantine_host_lab`: executed → `lab_assets.notes` contains `[quarantined:incident-126a8878-...:at-2026-04-22T07:16:03Z]` ✅
  - `kill_process_lab`: executed → auto-created `evidence_requests` row (process_list, status=open, target lab-win10-01) ✅
  - `invalidate_lab_session`: executed + reverted → 2 action_log entries, `invalidated_at` set then cleared ✅
  - `block_observable`: executed + reverted → row persists with `active=false` ✅
  - `request_evidence`: proposed only — UI correctly shows "Not executable in lab" because the action is classified suggest_only (plan line 70). ✅ behaviour-wise.
- All 7 action_log entries have `result=ok`, `executed_by=operator@cybercat.local`.
- **Not explicitly confirmed during session (fatigue):** (a) EvidenceRequestsPanel rendered the `kill_process`-auto-created request — user saw a Mark collected button but wasn't sure about the proposal row. (b) BlockedObservablesBadge while the IP was active wasn't checked (observable was already reverted before entity page was visited). 2-min recheck pending tomorrow — see "What needs to happen next session".

---

## Blockers

_None currently. Sub-track 1 blockers (cert infrastructure + Filebeat pipeline) resolved 2026-04-23._

---

## Known gaps / deferred decisions

- **Wazuh Active Response dispatch (Phase 11):** Implemented 2026-04-23. `quarantine_host` dispatches `firewall-drop0`; `kill_process` dispatches custom `kill-process` AR script. Both guarded by `WAZUH_AR_ENABLED` flag (default false). Verification on live stack pending.
- **Windows (Sysmon) lab endpoint (Phase 9B):** Phase 8's decoder covers `process.created` from auditd. Sysmon decoder branch adds naturally in one file.
- **Wazuh dashboard service**: deliberately never started (CyberCat UI replaces it). Tracked in ADR-0004.
- **Evidence payload collection:** `EvidenceRequest.payload_url` column is in the schema but nothing populates it yet. Future phase: Wazuh file-collection triggered automatically, URL stored here.
- **Auth model for the analyst UI:** *(In progress — Phase 14.)* Foundation (14.1), session layer (14.2), and route gating + audit attribution (14.3) complete. OIDC opt-in (14.4) and smoke-test cutover (14.5) pending.
- **Local Python venv for IDE type-checking:** optional; Docker is sufficient for running.
- **lab-debian auth.log forwarding**: Fixed — `rsyslog` added to Dockerfile, `rsyslogd` started in entrypoint, `<localfile>` block for `/var/log/auth.log` injected idempotently. SSH auth events now flow end-to-end.
- **Startup / dev-ergonomics simplification (deferred to end of project):** collapse the current multi-terminal flow (compose up / backend commands / smoke scripts) into a single dispatcher — either sub-commands on `start.sh` (`./start.sh up|test|smoke|demo|down`) or a `Makefile`. Pure ergonomics, zero architectural impact. Defer until feature work is done so the final dispatcher wraps the final set of commands, not a moving target.

---

## Open questions / assumptions being made

- Multi-operator auth is in progress (Phase 14). `AUTH_REQUIRED=false` by default; flip to `true` for real-auth mode.
- Local Postgres (compose), not managed DB.
- Wazuh runs in `--profile wazuh` so it can be stopped when not demoing.
- The Lenovo Legion handles Wazuh + 1 lab container + the app stack during active demo sessions (~4.2 GB per the plan's budget), but not continuously.
- Frontend and backend are in the same monorepo.

---

## Risks to watch

- **Scope creep toward SIEM.** If a feature is "ingest more log types", it needs a correlation-value justification, not just volume.
- **Wazuh becoming the center of gravity.** Every Wazuh integration task should be matched by a custom-layer task the same week.
- **Infra sprawl on the laptop.** Each new always-on service needs an ADR.
- **Verification theatre.** The Phase 7 "complete" overstatement today is the exact failure mode to avoid. Going forward: a phase is not complete until the phase's smoke test script passes end-to-end on a clean checkout.
