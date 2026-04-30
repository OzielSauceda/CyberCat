"""Phase 19 A1.1 — assert the streaming publisher does not block on a Redis outage.

When Redis is unavailable (DNS lookup hangs, container removed, etc.) the
streaming publisher must short-circuit quickly so the ingest path is not held
up by a slow redis call. Combined with the socket timeouts on
`init_redis()`, `safe_redis()` swallows the timeout/connection error and
returns the supplied default — the call site sees the default in well under
one second.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from app.streaming.publisher import publish


@pytest.mark.asyncio
async def test_publisher_does_not_block_on_outage():
    """A slow / failing Redis publish must not propagate latency to the caller."""

    async def _hangs_then_fails(*_args, **_kwargs):
        # Simulate the slow-failure pattern (e.g. socket_timeout firing): wait
        # briefly then raise. safe_redis must catch and return the default.
        await asyncio.sleep(0.05)
        from redis.exceptions import ConnectionError as RedisConnectionError
        raise RedisConnectionError("simulated outage")

    fake_client = MagicMock()
    fake_client.publish = _hangs_then_fails

    with patch("app.db.redis.get_redis", return_value=fake_client):
        start = time.monotonic()
        await publish("incident.created", {"incident_id": "test-id"})
        elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"publisher blocked for {elapsed:.2f}s on redis outage"
