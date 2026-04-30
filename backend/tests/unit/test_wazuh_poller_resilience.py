"""Phase 19 — Wazuh poller circuit-breaker resilience tests.

Asserts the per-hit ingest failure circuit-breaker:
- 0/10 ingest failures (all fine) → cursor advances past every hit, no exception.
- 3/10 ingest failures (transient) → cursor still advances past last hit,
  drop counter ticks, no breaker trip.
- 10/10 ingest failures (sustained) → breaker trips, raises WazuhPollerCircuitOpen,
  cursor is NOT advanced past failed hits.
- HTTP error from indexer → cursor not advanced, no breaker raise (separate path).

These tests use a stubbed httpx response and patch `ingest_normalized_event` so
we don't need a real Postgres + Redis stack.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ingest import wazuh_poller as poller_mod
from app.ingest.wazuh_poller import (
    _CONSECUTIVE_INGEST_FAIL_LIMIT,
    WazuhPollerCircuitOpen,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wazuh"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _make_hits(n: int) -> list[dict]:
    """N synthetic hits; each carries a unique `_id` and `sort` cursor."""
    base = _load_fixture("sshd-failed.json")
    hits = []
    for i in range(n):
        hit_id = f"AX{i:020d}"
        source = {**base, "_id": hit_id}
        hits.append({
            "_id": hit_id,
            "_source": source,
            "sort": [f"2026-04-21T10:00:{i:02d}.000Z", hit_id],
        })
    return hits


class _StubHttpResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "stub error",
                request=MagicMock(),
                response=MagicMock(status_code=self.status_code),
            )


def _stub_client(payload: dict) -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=_StubHttpResponse(payload))
    return client


# ---------------------------------------------------------------------------
# Helpers to capture cursor SQL writes without a real DB
# ---------------------------------------------------------------------------

class _CursorRecorder:
    """Stand-in for AsyncSessionLocal contexts. Records all SQL execute calls."""

    def __init__(self, cursor_value=None):
        self.cursor_value = cursor_value
        self.executes: list[tuple[str, dict]] = []
        self.commits = 0

    def __call__(self):
        return self  # AsyncSessionLocal() returns a context manager

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executes.append((sql, params or {}))
        result = MagicMock()
        if "SELECT search_after" in sql:
            result.fetchone = MagicMock(
                return_value=(self.cursor_value,) if self.cursor_value is not None else None
            )
        return result

    async def commit(self):
        self.commits += 1

    def cursor_advanced_to(self) -> str | None:
        """Return the JSON-encoded sort vector the cursor was advanced to, or None."""
        for sql, params in self.executes:
            if "search_after=CAST" in sql and "sa" in params:
                return params["sa"]
        return None

    def total_dropped(self) -> int:
        for sql, params in self.executes:
            if "events_dropped_total=events_dropped_total" in sql and "drp" in params:
                return params["drp"]
        return 0

    def total_accepted(self) -> int:
        for sql, params in self.executes:
            if "events_ingested_total=events_ingested_total" in sql and "acc" in params:
                return params["acc"]
        return 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def stop_event():
    import asyncio
    return asyncio.Event()


class TestCircuitBreaker:
    async def test_all_hits_succeed_advances_cursor_past_last(self, stop_event):
        hits = _make_hits(5)
        recorder = _CursorRecorder()

        async def fake_ingest(*_args, **_kwargs):
            mock = MagicMock()
            mock.dedup_hit = False
            return mock

        with patch.object(poller_mod, "AsyncSessionLocal", recorder), \
             patch.object(poller_mod, "ingest_normalized_event", new=fake_ingest), \
             patch.object(poller_mod, "_get_redis", create=True, new=lambda: MagicMock()), \
             patch("app.db.redis.get_redis", new=lambda: MagicMock()):
            client = _stub_client({"hits": {"hits": hits}})
            await poller_mod._poll_once(client, "http://stub/_search", stop_event)

        assert recorder.total_accepted() == 5
        assert recorder.total_dropped() == 0
        assert recorder.cursor_advanced_to() is not None
        # Cursor advanced to last hit's sort vector
        assert hits[-1]["_id"] in recorder.cursor_advanced_to()

    async def test_transient_failures_do_not_trip_breaker(self, stop_event):
        """3 of 10 hits fail to ingest, but not consecutively → cursor still advances."""
        hits = _make_hits(10)
        recorder = _CursorRecorder()
        call_count = {"n": 0}

        async def flaky_ingest(*_args, **_kwargs):
            call_count["n"] += 1
            # Fail every 4th call (positions 1, 5, 9 of 1-indexed) — never consecutive
            if call_count["n"] in (1, 5, 9):
                raise RuntimeError("transient ingest failure")
            mock = MagicMock()
            mock.dedup_hit = False
            return mock

        with patch.object(poller_mod, "AsyncSessionLocal", recorder), \
             patch.object(poller_mod, "ingest_normalized_event", new=flaky_ingest), \
             patch("app.db.redis.get_redis", new=lambda: MagicMock()):
            client = _stub_client({"hits": {"hits": hits}})
            await poller_mod._poll_once(client, "http://stub/_search", stop_event)

        assert recorder.total_accepted() == 7
        assert recorder.total_dropped() == 3
        # Cursor advanced to LAST hit (the streak never reached the limit)
        assert hits[-1]["_id"] in (recorder.cursor_advanced_to() or "")

    async def test_consecutive_failures_trip_breaker(self, stop_event):
        """Every hit fails consecutively → breaker trips, raises, cursor frozen."""
        hits = _make_hits(_CONSECUTIVE_INGEST_FAIL_LIMIT + 5)
        recorder = _CursorRecorder()

        async def always_fail(*_args, **_kwargs):
            raise RuntimeError("simulated sustained ingest failure")

        with patch.object(poller_mod, "AsyncSessionLocal", recorder), \
             patch.object(poller_mod, "ingest_normalized_event", new=always_fail), \
             patch("app.db.redis.get_redis", new=lambda: MagicMock()):
            client = _stub_client({"hits": {"hits": hits}})
            with pytest.raises(WazuhPollerCircuitOpen):
                await poller_mod._poll_once(client, "http://stub/_search", stop_event)

        # Cursor must NOT have advanced — last_sort was never set since no hit succeeded
        assert recorder.cursor_advanced_to() is None
        # Dropped count reflects exactly the hits we attempted before tripping
        assert recorder.total_dropped() == _CONSECUTIVE_INGEST_FAIL_LIMIT

    async def test_decode_failure_does_not_count_toward_breaker(self, stop_event):
        """All hits decode-fail → no breaker (poison-message handling is separate)."""
        hits = _make_hits(_CONSECUTIVE_INGEST_FAIL_LIMIT + 5)
        recorder = _CursorRecorder()

        with patch.object(poller_mod, "AsyncSessionLocal", recorder), \
             patch.object(poller_mod, "decode_wazuh_alert", return_value=None), \
             patch("app.db.redis.get_redis", new=lambda: MagicMock()):
            client = _stub_client({"hits": {"hits": hits}})
            # Should NOT raise — decoder rejections advance past poison messages.
            await poller_mod._poll_once(client, "http://stub/_search", stop_event)

        # All hits were dropped (decoded as None), but cursor still advanced
        assert recorder.total_dropped() == len(hits)
        assert recorder.cursor_advanced_to() is not None
        assert hits[-1]["_id"] in recorder.cursor_advanced_to()

    async def test_http_error_does_not_advance_cursor(self, stop_event):
        """5xx from indexer → cursor not advanced, no breaker raise."""
        recorder = _CursorRecorder()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(side_effect=httpx.ConnectError("indexer unreachable"))

        with patch.object(poller_mod, "AsyncSessionLocal", recorder), \
             patch.object(poller_mod, "_emit_wazuh_transition", new=AsyncMock()), \
             patch.object(poller_mod, "_interruptible_sleep", new=AsyncMock()):
            await poller_mod._poll_once(client, "http://stub/_search", stop_event)

        # No SELECT-then-advance cycle completed; no cursor advancement
        assert recorder.cursor_advanced_to() is None
