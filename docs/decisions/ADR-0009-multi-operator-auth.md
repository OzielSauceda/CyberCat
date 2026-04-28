# ADR-0009 — Multi-Operator Auth (Phase 14)

**Status:** Accepted  
**Date:** 2026-04-27  
**Deciders:** Oziel (owner)

---

## Context

CyberCat started as a single-operator, localhost-only tool. No auth existed; every endpoint was open. This was an acceptable shortcut for Phases 1–13 but created two real problems:

1. **No audit attribution.** Every incident transition, note, action log, and evidence-request row recorded `"operator@cybercat.local"` as the actor — a hardcoded string with no database identity behind it. This is the single biggest "toy project" tell in the audit trail.
2. **No access control.** Any process that could reach port 8000 could mutate anything. Adding a second human operator, a CI service account, or a read-only viewer required no code change but also offered no protection.

Phase 14's goal is to fix both: real per-user audit attribution, three-role access control, and an optional SSO path — without requiring a flag day on existing tests, smoke scripts, or demos.

---

## Decisions

### 1. Local-primary password auth + OIDC opt-in

**Chosen:** Email/password with bcrypt + HMAC-signed session cookies as the primary path. OIDC available as an opt-in overlay via four env vars.

**Rejected alternatives:**
- *OIDC-only* — operators running purely local labs (no IdP, no internet) need a functional auth path. A local password store with bcrypt is a dozen lines; requiring an IdP for a lab tool adds a hard dependency.
- *SAML* — SAML carries XML complexity (signed XML assertions, metadata exchange, SP/IdP cert management) with no benefit at this scale. Every major IdP that supports SAML also supports OIDC. SAML is omitted entirely; a future ADR can revisit if enterprise IdP integration is genuinely needed.

OIDC is opt-in: when `OIDC_PROVIDER_URL` is unset, the `/v1/auth/oidc/*` endpoints return HTTP 501. Setting all four env vars enables the SSO flow without touching the local-auth path.

### 2. Stateless session cookies + argon2-hashed API tokens

**Session cookies:** `itsdangerous.URLSafeTimedSerializer` — HMAC-signed, tamper-evident, TTL enforced at decode time. No Redis lookup per request. One 8-hour browser session per sign-in.

**API tokens:** `cct_`-prefixed 256-bit random tokens, stored as argon2 hashes in Postgres `api_tokens`. One DB query per Bearer-authenticated request (hash compare + user fetch, ~a few ms, acceptable at lab scale).

**Why not Redis sessions:** Redis is ephemeral coordination per `CLAUDE.md §2` — never the system of record. A Redis session store makes auth depend on Redis uptime and makes session revocation require Redis. Stateless cookies keep the same guarantee (`AUTH_REQUIRED=false` → `get_current_user` returns a synthetic sentinel that touches neither DB nor Redis).

**Accepted trade-off:** No server-side instant revocation of cookie sessions — the cookie is valid until it expires (8h) or the `AUTH_COOKIE_SECRET` rotates. For a lab tool used by a small known team, this is acceptable. API tokens are revocable immediately (delete the DB row).

### 3. Three-role model: admin / analyst / read_only

| Role | Mutation endpoints | Read endpoints | User management |
|------|-------------------|----------------|-----------------|
| `admin` | ✅ | ✅ | ✅ (via CLI or future PATCH) |
| `analyst` | ✅ | ✅ | ❌ |
| `read_only` | ❌ | ✅ | ❌ |

**Rejected alternatives:**
- *ABAC / policy engine* — CyberCat has one resource hierarchy and three real operating modes (full access, read+investigate, read-only). An ABAC policy DSL would add ~300 lines of policy code to model what three role checks already express. Add ABAC if the resource model grows significantly.
- *Two roles (admin + regular)* — read-only viewers (management, auditors, SOC observers) are a real operating mode that should not have the ability to execute response actions. Three roles covers it without complexity.

The six frontend mutation controls (`TransitionMenu`, Execute/Revert buttons, Mark collected/Dismiss, Post note, Propose action, Register/Remove lab asset) render `disabled` with a "Read-only role" tooltip for `read_only` sessions — the UI enforces the same contract the API does.

### 4. AUTH_REQUIRED feature flag, default false

`AUTH_REQUIRED=false` means `get_current_user` returns a synthetic `SystemUser` sentinel (not a DB row). `resolve_actor_id()` maps this sentinel to the `legacy@cybercat.local` UUID backfilled in migration 0007. All mutation routes and SSE still work; the gating dependencies are no-ops.

This default exists so that:
- All 156 existing pytest tests continue to pass unchanged.
- All 9 smoke scripts continue to pass without a `SMOKE_API_TOKEN`.
- Demo/dev runs don't require a bootstrap CLI step.

`AUTH_REQUIRED=true` is the production posture. It requires at least one user row (created via `python -m backend.app.auth.cli seed-admin`) and `AUTH_COOKIE_SECRET` set to a non-empty value before the stack starts.

### 5. JIT OIDC user provisioning, read_only default

When a new identity signs in via OIDC for the first time, a user row is created with `role=read_only`. An admin must elevate the role to `analyst` before the user can take mutating actions.

**Rejected alternative:** *Deny first sign-in until an admin pre-creates the row.* This creates friction for demos and POC deployments where the operator wants to log in immediately to verify SSO is working. JIT provisioning with a safe default (read_only) provides the same security posture while eliminating the friction.

**Lookup chain on callback:** `oidc_subject` match → `email` match → JIT create. This means an existing locally-created user with the same email transitions to SSO without losing their history or role.

---

## Consequences

- **Positive:** Every `ActionLog`, `IncidentTransition`, `Note`, `EvidenceRequest`, and `LabAsset` row now carries a real `actor_user_id` UUID. The audit trail is honest.
- **Positive:** OIDC opt-in means teams already using Google Workspace, Okta, Auth0, Keycloak, or Authentik get SSO with no code change — just four env vars.
- **Positive:** `AUTH_REQUIRED=false` default means zero flag-day impact on existing tooling. Tests, smoke scripts, and demos all pass unchanged until the operator explicitly turns on enforcement.
- **Neutral:** The auth system adds ~1–2 DB queries per authenticated request. At lab scale (single analyst, dozens of requests per minute) this is invisible.
- **Neutral:** Cookie sessions are not instantly revocable — the 8h TTL is the effective maximum session lifetime. Rotating `AUTH_COOKIE_SECRET` invalidates all active sessions immediately if emergency revocation is needed.
- **Deferred:** SAML, multi-tenant isolation, and fine-grained ABAC are all explicitly out of scope. If CyberCat ever targets enterprise deployment, these warrant their own ADRs.
