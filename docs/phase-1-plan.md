# Phase 1 Execution Plan — Project Scaffold + Ingest Skeleton

Scope: bring the stack up, lay the rails, accept events at the door. Read this first, then `docs/architecture.md` §2–3, then ADR-0001 / ADR-0002 / ADR-0003.

> **Retrospective note.** This document was reconstructed after the fact to fill the docs archive — Phases 1–3 were executed before the per-phase plan format was in place. It describes the scope, decisions, and verification gate that the work actually shipped against, in the same shape as later phase plans.

---

## 0. Why this phase matters

Nothing in CyberCat works until the rails are laid. Phase 1 is unglamorous on purpose: a clean repo layout, a `docker compose up` that brings the whole stack up on a laptop, a single `POST /v1/events/raw` endpoint that returns 202 even when there's nothing behind it yet, and three ADRs that pin the project's identity hard enough that future sessions can't quietly drift into "let's add Kafka."

The scaffold has to make four downstream phases easy: Phase 2 (normalization) needs Postgres reachable and a place to put the canonical schema; Phase 3 (detection + correlation) needs Redis up and ready; Phase 4 (frontend) needs the FastAPI router structure already grouped under `/v1/*`; Phase 5+ needs Alembic configured so migrations are reviewable in PRs from day one.

Locked-in design constraints from CLAUDE.md and the brief:
- **Compose-first, laptop-friendly.** No Kubernetes, no Helm, no Terraform. The whole platform comes up with one command.
- **Postgres-truth, Redis-ephemeral.** Schemas land in Postgres via Alembic. Redis is touched only by code that owns its ephemeral nature.
- **Defensive only.** No outbound scanning, no offensive tooling, no host modifications. The stack runs entirely in containers.

---

## 1. Pre-work

### 1a. Repo layout

```
cybercat/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers (will grow)
│   │   ├── db/           # SQLAlchemy session + models
│   │   ├── ingest/       # POST /v1/events/raw lives here
│   │   └── main.py       # FastAPI app factory
│   ├── alembic/          # migrations
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/              # Next.js 15 App Router
│   ├── package.json
│   └── Dockerfile
├── infra/
│   └── compose/
│       └── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── api-contract.md
│   ├── runbook.md
│   └── decisions/
├── labs/
└── start.sh
```

### 1b. ADRs to write before code

- **ADR-0001 — Project scope.** Identity + endpoint compromise focus. Defensive only. Lab-safe. Out of scope: SIEM, EDR, offensive tooling, multi-tenant SaaS. This is the "what we are not" door.
- **ADR-0002 — Tech stack.** Python + FastAPI; Postgres + Redis; Wazuh upstream; Sigma for portable detection; Next.js + TypeScript; Compose for runtime.
- **ADR-0003 — Resource plan.** Tier A (Postgres + Redis + backend + frontend) under ~650 MB idle; Tier B (Wazuh stack) on demand only. No service lives on the operator's host OS.

These three pin the rails. Subsequent phases reference them when reviewing scope creep.

---

## 2. Decisions locked for Phase 1

| Decision | Choice | Reason |
|---|---|---|
| Backend framework | FastAPI | async-native, OpenAPI for free, pydantic on the boundary. |
| ORM + driver | SQLAlchemy 2.x async + asyncpg | typed, mature, Alembic-compatible. |
| Migrations | Alembic from day one | every schema change reviewed in a PR; no ad-hoc DDL. |
| Redis client | redis-py async | only one option that matters; integrates cleanly with asyncio. |
| Frontend | Next.js 15 + App Router + TypeScript | matches `frontend/app/` layout used by every later phase. |
| Container runtime | Docker / Podman + Compose | laptop-shaped; ADR-0003. |
| Python deps manager | `uv` (via `pip install -e .` inside Dockerfile) | fast, lockable, works in CI. |
| API version prefix | `/v1` | breaking changes get `/v2`; never invisible. |
| Health endpoint | `GET /healthz` (not `/v1/healthz`) | infra-level probe, intentionally outside versioned API. |

---

## 3. Work plan

### 3.1 Compose stack

`infra/compose/docker-compose.yml`:
- `postgres:16-alpine` — single DB `cybercat`, single user, healthcheck via `pg_isready`.
- `redis:7-alpine` — no persistence required; healthcheck via `redis-cli ping`.
- `backend` — built from `backend/Dockerfile`, depends on postgres + redis healthy, exposes `:8000`.
- `frontend` — built from `frontend/Dockerfile`, exposes `:3000`.

Volumes: `postgres_data`, `redis_data`. Environment via `infra/compose/.env`.

### 3.2 Backend bootstrap

- `backend/app/main.py` — `create_app()` factory; mounts a CORS middleware (locked to `http://localhost:3000`); registers a `/healthz` route that returns `{status: "ok", version, env}`.
- `backend/app/db/session.py` — async engine + sessionmaker; reads `DATABASE_URL` from env.
- `backend/app/redis/client.py` — module-level lazy redis async client.
- `backend/app/api/routers/events.py` — `POST /v1/events/raw` skeleton: accepts any JSON body via `Request.json()`, returns `202 Accepted` with `{accepted: true, todo: "ingestion not yet implemented"}`. The endpoint exists so Phase 2 can wire its real implementation behind a stable URL.

### 3.3 Alembic + initial migration

- `alembic/env.py` configured to read `DATABASE_URL` and import `app.db.models` for autogenerate to work later.
- Migration `0000_init.py` — empty, marks the DB as "managed by Alembic." Real schema lands in Phase 2's migration `0001_initial_schema.py`.
- `start.sh` runs `alembic upgrade head` before starting the backend so containers come up with the DB at the latest revision.

### 3.4 Frontend bootstrap

- `npx create-next-app@latest frontend --app --typescript --tailwind --no-src-dir`
- Replace the default home page with a simple `app/page.tsx` placeholder ("CyberCat — Phase 1") so the container has something to serve.
- No API calls yet; Phase 4 wires the real frontend.

### 3.5 Documentation seeds

- `docs/architecture.md` — first draft of the layered diagram + component list.
- `docs/data-model.md` — table-of-contents only; tables get filled in as they land.
- `docs/api-contract.md` — initial `Conventions` section (problem-envelope error shape, `/v1` prefix, pagination cursor format).
- `docs/runbook.md` — boot sequence (`docker compose up -d`), how to seed events (`POST /v1/events/raw`), how to reset (`docker compose down -v`).

### 3.6 `start.sh`

Project-root convenience script. Brings up the core stack from `infra/compose/`, waits for backend health, prints the URLs (`:8000`, `:3000`).

---

## 4. Verification gate

Phase 1 is not done until all of these pass.

1. `docker compose up -d` from `infra/compose/` brings up postgres, redis, backend, frontend without errors. All services report healthy within 30s.
2. `curl http://localhost:8000/healthz` → `{"status":"ok","version":"0.1.0","env":"development"}` (200).
3. `curl http://localhost:3000/` → 200, placeholder page renders.
4. `curl -X POST http://localhost:8000/v1/events/raw -H 'Content-Type: application/json' -d '{}'` → 202 with the placeholder envelope.
5. `docker exec compose-postgres-1 psql -U cybercat -d cybercat -c "SELECT version_num FROM alembic_version;"` returns `0000`.
6. `docker exec compose-redis-1 redis-cli ping` → `PONG`.
7. `docker compose down -v && docker compose up -d` — full reset round-trips clean.
8. ADR-0001, ADR-0002, ADR-0003 written and committed under `docs/decisions/`.
9. `docs/runbook.md` documents the boot, seed-skeleton, and reset commands.

---

## 5. Out of scope for Phase 1

| Feature | Deferred to |
|---|---|
| Real ingestion logic (validate, normalize, persist) | Phase 2 |
| Any DB tables beyond Alembic's bookkeeping | Phase 2 |
| Detection rules / correlator | Phase 3 |
| Incident model + lifecycle | Phase 3 |
| Frontend routing, components, polling | Phase 4 |
| Wazuh integration | Phase 8 (ADR-0004) |
| Auth / login | Phase 14 |

---

## 6. Risks and mitigations

- **Compose env-var drift.** Dev `.env` and CI `.env` must agree. Mitigation: a single `infra/compose/.env.example` checked in; real `.env` gitignored.
- **Alembic autogenerate later won't see models.** Mitigation: import all models in `alembic/env.py`'s target metadata block from day one, even when there are none.
- **Windows host path quirks.** Compose volume mounts must use forward slashes. Documented in `docs/runbook.md`.
- **Next.js + Docker hot reload flakiness.** Mitigation: runbook provides a local `npm run dev` fallback for frontend development.

---

## 7. Handoff note for Phase 2

Phase 2 will need:
- The `POST /v1/events/raw` route to swap its skeleton body for the real validate → normalize → persist pipeline without changing the URL or returning shape (still 202; body becomes `{event_id, detections_fired, incident_touched}`).
- Alembic ready for the first real migration (`0001_initial_schema`) — events, entities, event_entities, incidents, detections, and the incident-junction tables all land in one go.
- The CORS allowlist already wired so the Phase 4 frontend has a clean path through.
