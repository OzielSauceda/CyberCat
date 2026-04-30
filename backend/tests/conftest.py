"""Shared fixtures for integration tests.

Integration tests require a running Postgres + Redis (use `docker compose up -d` first).
DATABASE_URL and REDIS_URL are read from environment; defaults target the Compose stack.
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Override env before importing app modules so settings pick up test values
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cybercat:cybercat@localhost:5432/cybercat")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
# AR is always disabled in tests unless a test explicitly patches settings
os.environ["WAZUH_AR_ENABLED"] = "false"

from app.auth.dependencies import require_user, require_analyst, SystemUser  # noqa: E402
from app.auth.models import UserRole  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.redis import close_redis, init_redis  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402  -- triggers detector + correlator registration
from app.streaming.bus import close_bus, init_bus  # noqa: E402


@pytest_asyncio.fixture(scope="session")
async def engine():
    url = os.environ["DATABASE_URL"]
    eng = create_async_engine(url, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def db_session(engine):
    """Create a fresh session per test; rollback after each test."""
    async with engine.connect() as conn:
        await conn.execute(text("BEGIN"))
        session_factory = sessionmaker(conn, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            yield session
        await conn.execute(text("ROLLBACK"))


@pytest_asyncio.fixture()
async def client():
    """HTTP client against the real app (Postgres + Redis must be up)."""
    await init_redis()
    await init_bus()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_bus()
    await close_redis()


_analyst_user = SystemUser(email="test-analyst@cybercat.local", role=UserRole.analyst)
_readonly_user = SystemUser(email="test-readonly@cybercat.local", role=UserRole.read_only)


def _make_analyst() -> SystemUser:
    return _analyst_user


def _make_readonly() -> SystemUser:
    return _readonly_user


@pytest_asyncio.fixture()
async def authed_client():
    """HTTP client authenticated as an analyst-role SystemUser (no DB required for auth)."""
    app.dependency_overrides[require_user] = _make_analyst
    app.dependency_overrides[require_analyst] = _make_analyst
    await init_redis()
    await init_bus()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_bus()
    await close_redis()
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_analyst, None)


@pytest_asyncio.fixture()
async def readonly_client():
    """HTTP client authenticated as a read_only-role SystemUser."""
    app.dependency_overrides[require_user] = _make_readonly
    app.dependency_overrides[require_analyst] = _make_readonly
    await init_redis()
    await init_bus()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_bus()
    await close_redis()
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_analyst, None)


@pytest.fixture()
def count_queries():
    """Phase 19: count SQL statements executed against the engine inside a `with` block.

    Usage::

        async def test_no_n_plus_1(count_queries, ...):
            with count_queries() as counter:
                resp = await client.get("/v1/incidents")
            assert counter.count <= 5
    """
    from contextlib import contextmanager

    from sqlalchemy import event

    from app.db.session import engine

    class _Counter:
        def __init__(self) -> None:
            self.count = 0
            self.statements: list[str] = []

    @contextmanager
    def _counter():
        c = _Counter()

        def _on_execute(_conn, _cursor, statement, *_args, **_kw):
            # Skip BEGIN/COMMIT/ROLLBACK noise — we care about real SQL.
            stripped = statement.strip().upper()
            if stripped.startswith(("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")):
                return
            c.count += 1
            c.statements.append(statement)

        sync_engine = engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", _on_execute)
        try:
            yield c
        finally:
            event.remove(sync_engine, "before_cursor_execute", _on_execute)

    return _counter


@pytest.fixture(autouse=True)
def _reset_redis_breaker():
    """Reset the safe_redis circuit breaker before/after every test so timeouts
    in one test cannot make safe_redis short-circuit in the next."""
    from app.db.redis_state import reset_throttle

    reset_throttle()
    yield
    reset_throttle()


@pytest_asyncio.fixture(autouse=False)
async def truncate_tables(client):
    """Truncate event/detection/incident tables AND flush Redis before a test that opts in.

    Redis flush is required because correlators (notably endpoint_compromise_standalone)
    keep SETNX dedupe keys with multi-hour TTLs. Without flushing, a key left over from a
    prior smoke test or manual curl blocks the correlator from opening a new incident.
    """
    from app.db.redis import get_redis
    from app.db.session import AsyncSessionLocal

    await get_redis().flushdb()

    tables = [
        "notes", "incident_transitions", "action_logs", "actions",
        "incident_attack", "incident_entities", "incident_events",
        "incident_detections", "incidents", "detections",
        "event_entities", "events", "entities",
        "evidence_requests", "blocked_observables", "lab_sessions",
        "lab_assets",
    ]

    async with AsyncSessionLocal() as session:
        for t in tables:
            await session.execute(text(f'TRUNCATE TABLE "{t}" CASCADE'))
        await session.commit()
    yield
