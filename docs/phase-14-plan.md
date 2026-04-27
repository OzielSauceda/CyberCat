# Phase 14 — Multi-Operator Auth + Audit — Implementation Plan

## Context

CyberCat today is a **single-operator** product. All API endpoints are open, every analyst action is attributed to the hardcoded string `"operator@cybercat.local"`, and there is no `users` table. This is the single biggest blocker between the current lab-grade product and "could actually run in a small SOC" (per `CyberCat-Explained.md` §16 item 10).

This feature adds:
1. **Local password auth** (primary, laptop-friendly, works offline) plus **OIDC opt-in** (one provider, env-driven).
2. **Three roles**: `admin`, `analyst`, `read_only`. Mutations require `analyst`+; user/token management requires `admin`.
3. **Per-user audit attribution** — every audit row gains a real `actor_user_id` FK, while existing free-text `actor` columns are kept for immutability (survives user deletion).
4. **Feature-flagged rollout** (`AUTH_REQUIRED=false` by default) so the existing 109-test suite, 8 smoke scripts, and dev-mode flow keep working unmodified during the transition.

Out of scope by deliberate choice (CLAUDE.md §4): SAML, multi-tenancy, fine-grained per-resource ACLs, MFA, SCIM. SAML omitted — too heavy for a "small SOC" target; OIDC subsumes the realistic provider list (Google Workspace, Okta, Auth0, Keycloak).

## Approach Summary

- **Sessions:** stateless HMAC-signed cookies (`itsdangerous.URLSafeTimedSerializer`) carrying `{user_id, role, token_version, exp}`. No DB lookup per request. Revocation by bumping `users.token_version`.
- **API tokens** (CLI/smoke tests): random 32-byte token with `cct_` prefix; only `sha256(token)` stored in `api_tokens` table. Bearer-token clients pass `Authorization: Bearer cct_…`.
- **SSE auth:** browser cookie carries automatically (EventSource sends cookies on same-origin). Bearer-token clients fall back to existing 60s polling safety net in `useStream`.
- **Cross-origin pain avoided** via Next.js dev-server `rewrites` proxying `/v1/*` to backend → browser sees one origin → SameSite=Lax cookies just work, no CORS+credentials dance.
- **Dev-mode bypass:** when `AUTH_REQUIRED=false`, dependencies return a `SystemUser` sentinel that resolves to a `legacy@cybercat.local` audit user at insert time. All existing tests, smoke scripts, and demos keep working.

## Schema (Migration `0007_multi_operator_auth.py`)

New tables:

| Table | Columns |
|---|---|
| `users` | `id` UUID pk, `email` citext unique, `password_hash` text nullable, `oidc_subject` text nullable unique, `role` enum('admin','analyst','read_only') NOT NULL default 'read_only', `is_active` bool NOT NULL default true, `token_version` int NOT NULL default 1, `created_at` timestamptz |
| `api_tokens` | `id` UUID pk, `user_id` FK→users, `name` text, `token_hash` bytea unique, `last_used_at` timestamptz nullable, `created_at` timestamptz, `revoked_at` timestamptz nullable |

Extend tables (all FKs nullable for migration safety):
- `incident_transitions` → add `actor_user_id` FK→users
- `action_logs` → add `actor_user_id` FK→users
- `notes` → add `actor_user_id` FK→users
- `evidence_requests` → add `collected_by_user_id`, `dismissed_by_user_id` FK→users
- `lab_assets` → add `created_by_user_id` FK→users

Backfill: insert one `users` row `legacy@cybercat.local` (role=analyst, is_active=false), set every existing audit row's `*_user_id` to its UUID. **Keep existing string columns** (`actor`, `executed_by`, `author`) as denormalized display values — never drop them.

Indexes: `users(email)`, `users(oidc_subject) WHERE oidc_subject IS NOT NULL`, `api_tokens(token_hash)`. Requires `CREATE EXTENSION IF NOT EXISTS citext`.

## Phased Rollout

### Phase 14.1 — Auth Foundation (feature-flagged, default off)

**Create:**
- `backend/app/auth/__init__.py` — package marker.
- `backend/app/auth/models.py` — `User`, `ApiToken` SQLAlchemy models.
- `backend/app/auth/security.py` — `hash_password`/`verify_password` (passlib[bcrypt]), `sign_session`/`verify_session` (itsdangerous), `hash_token`/`generate_token` (sha256 + secrets.token_urlsafe).
- `backend/app/auth/dependencies.py` — `get_current_user`, `require_user` (any role), `require_analyst`, `require_admin`. When `settings.auth_required=False`, returns a `SystemUser` dataclass; `resolve_actor_id(user, db)` helper looks up the legacy user and returns its UUID.
- `backend/app/auth/router.py` — `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me`, `GET /v1/auth/config` (public — returns `{auth_required, oidc_enabled}`), `POST /v1/auth/tokens`, `DELETE /v1/auth/tokens/{id}` (admin-only), `GET /v1/auth/users`, `PATCH /v1/auth/users/{id}/role` (admin-only).
- `backend/app/cli.py` — `seed-admin`, `create-user`, `set-role`, `issue-token`, `revoke-token`. Used to bootstrap the first admin and issue smoke-test tokens — **not network-callable**.
- `backend/alembic/versions/0007_multi_operator_auth.py` — schema + backfill above.
- `backend/tests/unit/test_auth_security.py` — bcrypt round-trip, cookie sign/verify with TTL, token hash uniqueness.
- `backend/tests/integration/test_auth_router.py` — login/logout/me/token CRUD, role enforcement on admin endpoints.

**Modify:**
- `backend/app/config.py` — add `auth_required: bool = False`, `auth_cookie_secret: str = ""` (validated non-empty when `auth_required=True`), `auth_cookie_name: str = "cybercat_session"`, `auth_session_ttl_minutes: int = 480`, `oidc_provider_url`, `oidc_client_id`, `oidc_client_secret`, `oidc_redirect_uri` (all `Optional[str] = None`).
- `backend/app/db/models.py` — relationships from `IncidentTransition` / `ActionLog` / `Note` / `EvidenceRequest` / `LabAsset` to `User`. Import `User` / `ApiToken` so Alembic autogen sees them.
- `backend/app/main.py` — register `auth_router`.
- `backend/pyproject.toml` — add `passlib[bcrypt]`, `itsdangerous`. (Defer `authlib` to Phase 14.4.)

**Verify:**
- `pytest backend/tests` — 109/109 still pass (default `auth_required=false`).
- New unit/integration tests pass.
- `alembic upgrade head` then `downgrade -1` round-trip clean.
- `python -m app.cli seed-admin --email admin@local --password 'changeme'` creates the row.

### Phase 14.2 — Frontend Login + Session

**Create:**
- `frontend/app/login/page.tsx` — email/password form posting to `/v1/auth/login`; on success redirects to `?next=` or `/`. Conditionally renders "Sign in with SSO" button when `/v1/auth/config` reports `oidc_enabled=true`.
- `frontend/app/lib/auth.ts` — `login()`, `logout()`, `getMe()`, `getAuthConfig()`, `User` type, `useCanMutate()` hook (`role === 'analyst' || role === 'admin'`).
- `frontend/app/lib/SessionContext.tsx` — React Context provider; fetches `/v1/auth/me` on mount; exposes `{user, status: 'loading'|'authed'|'anon', refresh, logout}`.
- `frontend/app/components/UserBadge.tsx` — header pill: email + role badge + "Sign out" link. When `status==='anon'` and `auth_required=true`, redirects to `/login`.

**Modify:**
- `frontend/app/lib/api.ts:184–210` — single change to the `request()` helper: add `credentials: "include"` to every fetch; on 401, `window.location.assign('/login?next=' + encodeURIComponent(location.pathname))` (skip if already on `/login`).
- `frontend/app/layout.tsx` — wrap children in `<SessionProvider>`; render `<UserBadge>` in the header `ml-auto` flex group between `<StreamStatusBadge />` and `<WazuhBridgeBadge />`.
- `frontend/next.config.js` — add `rewrites: [{ source: '/v1/:path*', destination: 'http://backend:8000/v1/:path*' }]` so browser sees same origin (eliminates SameSite=None+Secure requirement).

**Verify:** Manual — visit `/`, get redirected to `/login`; log in, see badge with email + role; reload preserves session; log out clears cookie. With `auth_required=false`, `/auth/me` returns the system user and login page is unreachable from normal navigation.

### Phase 14.3 — Route Gating + Audit Field Population

**Modify (route gating):**
- `backend/app/api/routers/responses.py` — `Depends(require_analyst)` on propose/execute/revert. Replace lines 131 + 177 hardcoded strings with `current_user.email`; pass `actor_user_id=current_user.id` (or resolved legacy id) into `execute_action`/`revert_action`.
- `backend/app/api/routers/incidents.py` — `require_analyst` on POST transitions + POST notes. Replace lines 429 + 484; populate `actor_user_id`.
- `backend/app/api/routers/evidence_requests.py` — `require_analyst` on collect/dismiss; populate `collected_by_user_id` / `dismissed_by_user_id`.
- `backend/app/api/routers/lab_assets.py` — `require_analyst` on POST/DELETE; populate `created_by_user_id`.
- `backend/app/api/routers/events.py` — `require_analyst` on `POST /events/raw` (the simulator and smoke scripts use service tokens here).
- All GET routers + `streaming.py` SSE: `Depends(require_user)` (analyst, admin, read_only all pass).
- `backend/app/response/executor.py` — `execute_action` / `revert_action` signatures gain optional `actor_user_id: UUID | None` parameter; populated into `ActionLog`.

**Modify (Pydantic schemas):**
- `backend/app/api/schemas/incidents.py` — `ActionLogSummary`, `TransitionRef`, `NoteRef` gain optional `actor_user_id: UUID | None`. Existing `executed_by` / `actor` / `author` strings stay (now sourced from the user's email at write time).

**Modify (frontend gates):** Add `disabled={!canMutate}` + a tooltip "Read-only role" on:
- `frontend/app/components/TransitionMenu.tsx` (transition button)
- `frontend/app/incidents/[id]/ActionControls.tsx` (Execute, Revert buttons)
- `frontend/app/components/EvidenceRequestsPanel.tsx` (Mark collected, Dismiss)
- `frontend/app/incidents/[id]/NotesPanel.tsx` (textarea + Post note button) — also remove the hardcoded `author: "operator@cybercat.local"` placeholder at line 41.
- `frontend/app/incidents/[id]/ProposeActionModal.tsx` (Propose submit)
- `frontend/app/lab/page.tsx` (Register asset, Remove asset)

**Modify (tests):**
- `backend/tests/conftest.py` — add `authed_client` and `readonly_client` fixtures using `app.dependency_overrides[require_user] = lambda: test_user`. Default `client` fixture stays anonymous (relies on `auth_required=false`) so the existing 109 tests don't change.
- New `backend/tests/integration/test_auth_gating.py` — parameterized over `[(method, path, required_role), …]`. Asserts each mutation route returns 401 for anonymous + 403 for `read_only`. **This list is the canonical inventory** — adding a new mutation route without updating this list fails CI, preventing silent privilege bypass.

**Verify:** existing 109 still green; new gating tests green; manual log-in as `read_only` confirms buttons render disabled and direct `curl` returns 403.

### Phase 14.4 — OIDC Opt-in

**Create:**
- `backend/app/auth/oidc.py` — `authlib` OAuth client init (lazy, only if `oidc_provider_url` set), `start_login`, `handle_callback`, JIT user provisioning (role defaults to `read_only`; admin elevates via CLI or `PATCH /auth/users/{id}/role`).

**Modify:**
- `backend/app/auth/router.py` — add `GET /v1/auth/oidc/login` (302 to provider) and `GET /v1/auth/oidc/callback` (verify state, fetch userinfo, upsert user matched by `oidc_subject` first then by `email`, set session cookie, redirect to `/`).
- `backend/app/main.py` lifespan — initialize `authlib` client + JWKS cache when `oidc_provider_url` is configured; store on `app.state.oidc`.
- `backend/pyproject.toml` — add `authlib`. (`httpx` already present.)
- `frontend/app/login/page.tsx` — show "Sign in with SSO" button conditionally on `auth_config.oidc_enabled`.
- `docs/runbook.md` — provider setup walkthrough (Authentik / Keycloak / Google Workspace example).

**Verify:** Stand up `mock-oauth2-server` Docker image in a transient `docker-compose.test.yml` profile; integration test the full redirect dance. Manual: configure against real provider; log in via SSO; admin elevates the JIT-provisioned account to analyst.

### Phase 14.5 — Smoke Tests + Documentation + Cutover

**Modify:**
- All 8 `labs/smoke_test_phase*.sh` — source `labs/.smoke-env` (gitignored) for `SMOKE_API_TOKEN`; pass `-H "Authorization: Bearer $SMOKE_API_TOKEN"` on every curl. Wrap in: `[ -n "$SMOKE_API_TOKEN" ] && AUTH_HEADER=(-H "Authorization: Bearer $SMOKE_API_TOKEN") || AUTH_HEADER=()` so scripts also work in `auth_required=false` mode.
- `labs/.smoke-env.example` (new) — documents the variable.
- `infra/compose/docker-compose.yml` — add `AUTH_REQUIRED=false` and `AUTH_COOKIE_SECRET=` (operator fills) to backend env.
- `infra/compose/.env.example` — same.
- `docs/decisions/ADR-0009-multi-operator-auth.md` (new) — design record: local-primary + OIDC opt-in, stateless cookies, three-role model, reasoning for SAML omission.
- `docs/api-contract.md` — replace the "auth deferred" note with the real auth surface.
- `docs/runbook.md` — bootstrap flow: `cli seed-admin`, log in, create users, issue smoke tokens.
- `PROJECT_STATE.md` — log the new phase under "Phase-by-phase state".
- `project-explanation/CyberCat-Explained.md` §16 item 10 — mark done; §15 — bump phase count.

**Verify (cutover):**
1. `AUTH_REQUIRED=false` (default): all 8 smoke tests pass without env var. Existing demo flow unchanged.
2. `AUTH_REQUIRED=true`, `SMOKE_API_TOKEN` set: all 8 smoke tests pass.
3. `AUTH_REQUIRED=true`, no token: smoke tests fail with 401 (negative test confirms gating).
4. Browser: log in as analyst, open an incident, take an action, verify SSE updates the badge live (cookies travel on EventSource — confirm in DevTools Network → EventStream).
5. Browser: log in as `read_only`, confirm all 7 mutation buttons render disabled with tooltip; confirm direct `curl` to a mutation endpoint returns 403.
6. `pytest backend/tests` — 109 existing pass + ~20 new auth/gating tests pass.
7. `npm run typecheck` — 0 errors.

## Critical Files

**New (foundation):**
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\auth\dependencies.py` — gating + `SystemUser` sentinel (the single most important file)
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\auth\security.py` — bcrypt + cookie + token primitives
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\auth\router.py` — login/logout/me/users/tokens endpoints
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\cli.py` — bootstrap CLI (seed-admin, issue-token)
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\alembic\versions\0007_multi_operator_auth.py` — schema + backfill
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\tests\integration\test_auth_gating.py` — parameterized gate inventory (CI safety net)
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\frontend\app\login\page.tsx`
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\frontend\app\lib\SessionContext.tsx`
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\frontend\app\lib\auth.ts`
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\docs\decisions\ADR-0009-multi-operator-auth.md`

**Modified (single injection points — change once, propagates):**
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\config.py` — auth + OIDC settings
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\main.py` — auth router + lifespan
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\db\models.py` — FK relationships to `User`
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\app\response\executor.py` — `actor_user_id` plumbed
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\backend\tests\conftest.py` — `authed_client` + `readonly_client` fixtures
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\frontend\app\lib\api.ts:184–210` — `credentials: include` + 401 redirect
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\frontend\app\layout.tsx` — `<SessionProvider>` + `<UserBadge>`
- `C:\Users\oziel\OneDrive\Desktop\CyberCat\frontend\next.config.js` — `/v1/*` rewrite to backend
- All 5 mutation routers (`responses.py`, `incidents.py`, `evidence_requests.py`, `lab_assets.py`, `events.py`) — add `Depends(require_analyst)` + replace hardcoded actor strings (4 known sites)
- 6 frontend mutation components — `disabled={!canMutate}` + tooltip

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Adding a new mutation route later without gating it = silent privilege bypass | `test_auth_gating.py` parameterized inventory fails CI when a mutation method appears on a route absent from the list |
| Alembic autogen mishandles cross-package model imports | Explicitly import `User`, `ApiToken` in `db/models.py`; `alembic revision --autogenerate --sql` dry-run before commit |
| Cookie cross-origin breakage (frontend :3000, backend :8000) | Next.js `rewrites` proxies `/v1/*` so browser sees one origin; SameSite=Lax works without exception |
| EventSource can't carry bearer tokens | Browser uses cookie auth (carries automatically). Bearer-token (CLI) clients use existing `useStream` 60s polling fallback. Documented in ADR-0009. |
| Existing 109 tests break on auth flag flip | `AUTH_REQUIRED=false` default + `SystemUser` sentinel means dev mode and tests behave identically to today; cutover happens only when operator flips the flag |
| Smoke scripts hard-break when flag flips | Scripts gated on `[ -n "$SMOKE_API_TOKEN" ]`; absence = pre-cutover behavior, presence = post-cutover behavior — same script works in both modes |
| Lost admin password / can't get back in | CLI `seed-admin` is operator-local (DB-direct), can always reset; documented in runbook |
| `password_hash` plaintext leak in DB dumps | bcrypt cost 12; column never in API responses; `User` Pydantic schema explicitly excludes it |
| Token leak in logs | `auth_router.py` returns plaintext token **once** at creation; only `sha256(token)` ever stored; FastAPI access-log middleware stays default (no body logging) |

## Final End-to-End Verification

After all 5 sub-phases complete, the green-light checklist:
1. `alembic upgrade head` clean → migration 0007 applied.
2. `pytest backend/tests` → 109 baseline + ~20 new = ~130 tests, all green.
3. `npm run typecheck` → 0 errors.
4. With `AUTH_REQUIRED=false`: all 8 smoke scripts pass unmodified; analyst UI unchanged.
5. With `AUTH_REQUIRED=true` + admin seeded + smoke token issued: all 8 smoke scripts pass with `Authorization: Bearer …` header.
6. Browser dual-tab test: log in as analyst on tab 1, log in as read_only on tab 2; analyst takes action on incident; both tabs see live SSE update; tab 2's mutation buttons stay disabled.
7. Browser test: 401 redirect to `/login?next=…` works from a deep page (`/incidents/abc`); after login, lands back at `/incidents/abc`.
8. OIDC test (Phase 14.4): mock-oauth2-server in `docker-compose.test.yml` profile; full redirect dance succeeds; JIT-provisioned user gets `role=read_only`; admin elevates via CLI or `/auth/users/{id}/role`.
