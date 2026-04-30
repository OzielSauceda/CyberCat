"""Phase 19 — assert detectors degrade gracefully when Redis is unreachable.

Each detector that touches Redis is exercised against a mock client whose every
method raises `redis.ConnectionError`. The expected behavior:

- `auth_failed_burst`     — returns [] (cannot count without windowing)
- `auth_anomalous_source_success` — returns [] (premise unverifiable)
- `blocked_observable`    — falls back to the authoritative DB query and still
                            fires when a blocked value is present in Postgres.

The safe_redis helper is also expected to log a single throttled warning per
(rule_id, op_name) per minute. We verify the log is emitted but do not assert
on its frequency here — that's covered separately.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.db.models import Event
from app.db.redis_state import RedisUnavailable, reset_throttle, safe_redis
from app.detection.rules.auth_anomalous_source_success import (
    RULE_ID as ANOM_RULE,
    auth_anomalous_source_success,
)
from app.detection.rules.auth_failed_burst import (
    RULE_ID as AFB_RULE,
    auth_failed_burst,
)
from app.detection.rules.blocked_observable import (
    RULE_ID as BO_RULE,
    blocked_observable_check,
)
from app.enums import EventSource


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

def _failing_redis() -> MagicMock:
    """A redis-like mock whose every awaited method raises ConnectionError."""
    redis_mock = MagicMock()

    async def _fail(*_args, **_kwargs):
        raise RedisConnectionError("simulated redis outage")

    for op in ("exists", "incr", "expire", "set", "get", "delete"):
        setattr(redis_mock, op, AsyncMock(side_effect=_fail))
    return redis_mock


class _MockResult:
    def __init__(self, rows: list):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._rows[0] if self._rows else 0


def _mock_db(rows: list | None = None) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_MockResult(rows or []))
    return db


def _make_event(kind: str, normalized: dict) -> Event:
    return Event(
        id=uuid.uuid4(),
        source=EventSource.direct,
        kind=kind,
        occurred_at=datetime.now(timezone.utc),
        raw={},
        normalized=normalized,
    )


@pytest.fixture(autouse=True)
def _clear_throttle():
    reset_throttle()
    yield
    reset_throttle()


# ---------------------------------------------------------------------------
# safe_redis helper
# ---------------------------------------------------------------------------

class TestSafeRedis:
    async def test_returns_value_on_success(self):
        async def ok():
            return 42

        result = await safe_redis(ok(), rule_id="test", op_name="op", default=0)
        assert result == 42

    async def test_returns_default_on_redis_error(self):
        async def boom():
            raise RedisConnectionError("simulated")

        result = await safe_redis(boom(), rule_id="test", op_name="op", default="fallback")
        assert result == "fallback"

    async def test_returns_default_on_redis_unavailable(self):
        async def boom():
            raise RedisUnavailable("not initialised")

        result = await safe_redis(boom(), rule_id="test", op_name="op", default=None)
        assert result is None

    async def test_logs_warning_once_per_window(self, caplog):
        async def boom():
            raise RedisConnectionError("simulated")

        with caplog.at_level(logging.WARNING, logger="app.db.redis_state"):
            for _ in range(5):
                await safe_redis(boom(), rule_id="test", op_name="op", default=None)
        warnings = [r for r in caplog.records if "redis_degraded" in r.getMessage()]
        assert len(warnings) == 1, f"expected throttled to 1 log, got {len(warnings)}"


# ---------------------------------------------------------------------------
# auth_failed_burst
# ---------------------------------------------------------------------------

class TestAuthFailedBurstDegrade:
    async def test_returns_empty_when_redis_down(self):
        event = _make_event("auth.failed", {"user": "alice"})
        result = await auth_failed_burst(event, _mock_db(), _failing_redis())
        assert result == []

    async def test_does_not_raise_when_redis_down(self):
        event = _make_event("auth.failed", {"user": "bob"})
        # Must not raise.
        await auth_failed_burst(event, _mock_db(), _failing_redis())

    async def test_logs_degradation(self, caplog):
        event = _make_event("auth.failed", {"user": "carol"})
        with caplog.at_level(logging.WARNING, logger="app.db.redis_state"):
            await auth_failed_burst(event, _mock_db(), _failing_redis())
        assert any(
            f"rule={AFB_RULE}" in r.getMessage() and "redis_degraded" in r.getMessage()
            for r in caplog.records
        ), "expected redis_degraded warning for auth_failed_burst"


# ---------------------------------------------------------------------------
# auth_anomalous_source_success
# ---------------------------------------------------------------------------

class TestAnomalousSourceSuccessDegrade:
    async def test_returns_empty_when_redis_down(self):
        event = _make_event(
            "auth.succeeded", {"user": "alice", "source_ip": "203.0.113.5"}
        )
        result = await auth_anomalous_source_success(event, _mock_db(), _failing_redis())
        assert result == []

    async def test_does_not_raise_when_redis_down(self):
        event = _make_event(
            "auth.succeeded", {"user": "bob", "source_ip": "198.51.100.7"}
        )
        await auth_anomalous_source_success(event, _mock_db(), _failing_redis())

    async def test_logs_degradation(self, caplog):
        event = _make_event(
            "auth.succeeded", {"user": "carol", "source_ip": "203.0.113.9"}
        )
        with caplog.at_level(logging.WARNING, logger="app.db.redis_state"):
            await auth_anomalous_source_success(event, _mock_db(), _failing_redis())
        assert any(
            f"rule={ANOM_RULE}" in r.getMessage() for r in caplog.records
        )


# ---------------------------------------------------------------------------
# blocked_observable — DB fallback path
# ---------------------------------------------------------------------------

class TestBlockedObservableDegrade:
    async def test_no_match_when_db_empty_and_redis_down(self):
        event = _make_event("network.connection", {"dst_ip": "203.0.113.42"})
        result = await blocked_observable_check(event, _mock_db([]), _failing_redis())
        assert result == []

    async def test_fires_from_db_when_redis_down(self):
        # DB returns one blocked observable matching the event's dst_ip.
        db = _mock_db([("203.0.113.42",)])
        event = _make_event("network.connection", {"dst_ip": "203.0.113.42"})
        result = await blocked_observable_check(event, db, _failing_redis())
        assert len(result) == 1, "expected detection to fire from DB fallback"
        assert result[0].rule_id == BO_RULE
        assert result[0].matched_fields == {
            "matched_field": "dst_ip",
            "matched_value": "203.0.113.42",
        }

    async def test_does_not_raise_on_set_cache_failure(self):
        # DB has values; redis.set fails — must still return populated result.
        db = _mock_db([("198.51.100.50",)])
        event = _make_event("network.connection", {"src_ip": "198.51.100.50"})
        result = await blocked_observable_check(event, db, _failing_redis())
        assert len(result) == 1
        assert result[0].rule_id == BO_RULE


# ---------------------------------------------------------------------------
# get_redis sentinel path
# ---------------------------------------------------------------------------

class TestGetRedisRaisesUnavailable:
    async def test_raises_redis_unavailable_when_not_initialised(self):
        from app.db import redis as redis_module

        original = redis_module._client
        redis_module._client = None
        try:
            with pytest.raises(RedisUnavailable):
                redis_module.get_redis()
        finally:
            redis_module._client = original
