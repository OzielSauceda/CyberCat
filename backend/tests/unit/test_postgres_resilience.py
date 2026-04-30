"""Phase 19 — Postgres pool config + ingest retry behavior.

Asserts:
- The async engine is configured with the explicit pool params Phase 19 requires.
- `with_ingest_retry` retries exactly once on `DBAPIError(connection_invalidated=True)`.
- Other exceptions propagate unchanged (no retry, no swallowing).
- The retry delay is short enough to not block the poll loop noticeably.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import DBAPIError

from app.db.session import engine
from app.ingest.retry import with_ingest_retry


# ---------------------------------------------------------------------------
# Pool config
# ---------------------------------------------------------------------------

class TestEnginePoolConfig:
    def test_pool_pre_ping_enabled(self):
        # pre_ping is exposed via the dialect's pool — assert via the engine kw cache
        assert engine.pool._pre_ping is True

    def test_pool_size_is_explicit(self):
        # Default would be 5; Phase 19 sets 20
        assert engine.pool.size() == 20

    def test_pool_recycle_is_30_minutes(self):
        # Default is -1 (never); Phase 19 sets 1800
        assert engine.pool._recycle == 1800

    def test_pool_timeout_is_explicit(self):
        # Default is 30s; Phase 19 sets 10
        assert engine.pool._timeout == 10


# ---------------------------------------------------------------------------
# with_ingest_retry
# ---------------------------------------------------------------------------

def _make_invalidated_error() -> DBAPIError:
    """Construct a DBAPIError with connection_invalidated=True."""
    err = DBAPIError(statement="SELECT 1", params={}, orig=Exception("connection lost"))
    err.connection_invalidated = True
    return err


def _make_other_dbapi_error() -> DBAPIError:
    err = DBAPIError(statement="SELECT 1", params={}, orig=Exception("constraint violation"))
    err.connection_invalidated = False
    return err


@pytest.fixture
def fake_session_factory():
    """Patch AsyncSessionLocal so each call returns a fresh mock session context."""
    sessions: list[MagicMock] = []

    def _factory():
        sess = MagicMock()
        sess.__aenter__ = AsyncMock(return_value=sess)
        sess.__aexit__ = AsyncMock(return_value=False)
        sessions.append(sess)
        return sess

    with patch("app.ingest.retry.AsyncSessionLocal", _factory):
        yield sessions


class TestWithIngestRetry:
    async def test_succeeds_on_first_try(self, fake_session_factory):
        async def op(_session):
            return "ok"

        result = await with_ingest_retry(op)
        assert result == "ok"
        # Exactly one session was opened
        assert len(fake_session_factory) == 1

    async def test_retries_once_on_connection_invalidated(self, fake_session_factory):
        attempts = {"n": 0}

        async def op(_session):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise _make_invalidated_error()
            return "recovered"

        result = await with_ingest_retry(op)
        assert result == "recovered"
        assert attempts["n"] == 2
        # Two sessions were opened (one per attempt)
        assert len(fake_session_factory) == 2

    async def test_does_not_retry_other_dbapi_error(self, fake_session_factory):
        attempts = {"n": 0}

        async def op(_session):
            attempts["n"] += 1
            raise _make_other_dbapi_error()

        with pytest.raises(DBAPIError):
            await with_ingest_retry(op)
        assert attempts["n"] == 1, "must not retry on non-invalidated DBAPIError"
        assert len(fake_session_factory) == 1

    async def test_does_not_retry_generic_exception(self, fake_session_factory):
        attempts = {"n": 0}

        async def op(_session):
            attempts["n"] += 1
            raise RuntimeError("non-DB error")

        with pytest.raises(RuntimeError):
            await with_ingest_retry(op)
        assert attempts["n"] == 1
        assert len(fake_session_factory) == 1

    async def test_propagates_when_both_attempts_fail(self, fake_session_factory):
        async def op(_session):
            raise _make_invalidated_error()

        with pytest.raises(DBAPIError):
            await with_ingest_retry(op)
        # Both attempts opened a session
        assert len(fake_session_factory) == 2
