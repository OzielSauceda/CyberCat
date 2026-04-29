"""Tests for cct_agent.shipper.Shipper.

Uses respx to mock the backend HTTP surface. Covers:
  - 201 happy path
  - 4xx never retries (drop + log)
  - 5xx retries with backoff and eventually gives up
  - Network errors retry
  - Queue overflow drops oldest and counts
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from cct_agent.config import AgentConfig
from cct_agent.shipper import Shipper

API_BASE = "http://backend.test"


def _config(**overrides: Any) -> AgentConfig:
    base: dict[str, Any] = {
        "api_url": API_BASE,
        "agent_token": "test-token-xxxx",
        "log_path": "/tmp/auth.log",
        "checkpoint_path": "/tmp/cp.json",
        "host_name": "lab-debian",
        "batch_size": 5,
        "flush_interval_seconds": 0.05,
        "queue_max": 3,
        "poll_interval_seconds": 0.05,
    }
    base.update(overrides)
    return AgentConfig(**base)


def _event(kind: str = "auth.failed", user: str = "u") -> dict[str, Any]:
    return {
        "source": "direct",
        "kind": kind,
        "occurred_at": "2026-04-28T11:00:00+00:00",
        "raw": {"u": user},
        "normalized": {"user": user, "source_ip": "1.2.3.4", "auth_type": "password"},
        "dedupe_key": f"direct:{kind}:{user}",
    }


# ---------------------------------------------------------------------------
# Queue mechanics (no HTTP calls; doesn't need respx)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_under_capacity_no_drop():
    s = Shipper(_config(queue_max=3))
    await s.enqueue(_event(user="a"))
    await s.enqueue(_event(user="b"))
    assert s.dropped_count == 0
    assert s.queue.qsize() == 2


@pytest.mark.asyncio
async def test_enqueue_at_capacity_drops_oldest():
    s = Shipper(_config(queue_max=2))
    await s.enqueue(_event(user="a"))
    await s.enqueue(_event(user="b"))
    await s.enqueue(_event(user="c"))  # forces drop of "a"

    assert s.dropped_count == 1
    assert s.queue.qsize() == 2
    drained = [s.queue.get_nowait()["normalized"]["user"] for _ in range(2)]
    assert drained == ["b", "c"]


# ---------------------------------------------------------------------------
# HTTP shipping (respx-mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_201_happy_path():
    s = Shipper(_config())
    stop = asyncio.Event()

    with respx.mock(base_url=API_BASE) as mock:
        mock.post("/v1/events/raw").mock(
            return_value=httpx.Response(
                201,
                json={
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "dedup_hit": False,
                    "detections_fired": [],
                    "incident_touched": None,
                },
            )
        )

        await s.enqueue(_event(user="alice"))

        # Run the shipper, then stop it as soon as the event ships.
        async def _stopper():
            for _ in range(50):
                if s.shipped_count >= 1:
                    stop.set()
                    return
                await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(s.run(stop), _stopper())

    assert s.shipped_count == 1
    assert s.failed_count == 0


@pytest.mark.asyncio
async def test_4xx_never_retries_and_drops():
    s = Shipper(_config())
    stop = asyncio.Event()

    with respx.mock(base_url=API_BASE) as mock:
        route = mock.post("/v1/events/raw").mock(
            return_value=httpx.Response(
                422, json={"error": {"code": "normalized_shape_mismatch"}}
            )
        )

        await s.enqueue(_event(user="bob"))

        async def _stopper():
            for _ in range(50):
                if s.failed_count >= 1:
                    stop.set()
                    return
                await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(s.run(stop), _stopper())

    assert s.shipped_count == 0
    assert s.failed_count == 1
    # Exactly one POST: a 4xx must NOT trigger retries.
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds():
    s = Shipper(_config())
    stop = asyncio.Event()

    with respx.mock(base_url=API_BASE) as mock:
        route = mock.post("/v1/events/raw").mock(
            side_effect=[
                httpx.Response(503, text="overloaded"),
                httpx.Response(503, text="overloaded"),
                httpx.Response(
                    201,
                    json={
                        "event_id": "00000000-0000-0000-0000-000000000002",
                        "dedup_hit": False,
                        "detections_fired": [],
                        "incident_touched": None,
                    },
                ),
            ]
        )

        await s.enqueue(_event(user="carol"))

        async def _stopper():
            for _ in range(200):
                if s.shipped_count >= 1:
                    stop.set()
                    return
                await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(s.run(stop), _stopper())

    assert s.shipped_count == 1
    assert s.failed_count == 0
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_network_error_retries_then_succeeds():
    s = Shipper(_config())
    stop = asyncio.Event()

    with respx.mock(base_url=API_BASE) as mock:
        route = mock.post("/v1/events/raw").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(
                    201,
                    json={
                        "event_id": "00000000-0000-0000-0000-000000000003",
                        "dedup_hit": False,
                        "detections_fired": [],
                        "incident_touched": None,
                    },
                ),
            ]
        )

        await s.enqueue(_event(user="dave"))

        async def _stopper():
            for _ in range(200):
                if s.shipped_count >= 1:
                    stop.set()
                    return
                await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(s.run(stop), _stopper())

    assert s.shipped_count == 1
    assert s.failed_count == 0
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_persistent_5xx_eventually_gives_up():
    """After max_attempts of 5xx, the shipper drops the event and counts a failure."""
    s = Shipper(_config())
    stop = asyncio.Event()

    with respx.mock(base_url=API_BASE) as mock:
        route = mock.post("/v1/events/raw").mock(
            return_value=httpx.Response(503, text="still overloaded")
        )

        await s.enqueue(_event(user="erin"))

        # The shipper retries with growing backoff; 5 attempts at base 1s
        # but capped at 15s total backoff = ~31s worst case. Allow a generous
        # timeout but rely on the failure_count signal.
        async def _stopper():
            for _ in range(700):
                if s.failed_count >= 1:
                    stop.set()
                    return
                await asyncio.sleep(0.1)
            stop.set()

        await asyncio.gather(s.run(stop), _stopper())

    assert s.failed_count == 1
    assert s.shipped_count == 0
    # Five attempts (per _MAX_ATTEMPTS_PER_EVENT)
    assert route.call_count == 5


@pytest.mark.asyncio
async def test_authorization_header_is_set():
    """Bearer token from config must be sent on every request."""
    s = Shipper(_config(agent_token="secret-bearer-XYZ"))
    stop = asyncio.Event()

    with respx.mock(base_url=API_BASE) as mock:
        route = mock.post("/v1/events/raw").mock(
            return_value=httpx.Response(
                201,
                json={
                    "event_id": "00000000-0000-0000-0000-000000000004",
                    "dedup_hit": False,
                    "detections_fired": [],
                    "incident_touched": None,
                },
            )
        )

        await s.enqueue(_event(user="frank"))

        async def _stopper():
            for _ in range(50):
                if s.shipped_count >= 1:
                    stop.set()
                    return
                await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(s.run(stop), _stopper())

    auth_header = route.calls[0].request.headers.get("authorization")
    assert auth_header == "Bearer secret-bearer-XYZ"
