"""HTTP shipper: drains the in-memory event queue and POSTs to the backend.

Design notes:

  - **Bounded in-memory queue.** Drop-oldest under pressure (counted in
    ``dropped_count``). No disk spool in v1 — this is a lab tool against a
    backend that lives one container away. Phase 18 may add durable spool
    if needed.
  - **Exponential backoff** on 5xx and ``httpx.RequestError`` (network
    failure / backend not yet reachable). Bounded retries per event so a
    single malformed line does not block the queue indefinitely. After
    max_attempts, the event is dropped and counted in ``failed_count``.
  - **Never retry 4xx.** A 4xx from ``/v1/events/raw`` means our payload
    is malformed (missing field, unknown kind). Retrying loops forever
    on the same garbage. Log + drop.
  - **At-least-once delivery.** Events carry a deterministic ``dedupe_key``
    so backend dedup deduplicates a re-shipped event after a transient
    network blip.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from cct_agent.config import AgentConfig

log = logging.getLogger(__name__)

_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 15.0
_MAX_ATTEMPTS_PER_EVENT = 5


class Shipper:
    """Drain a queue of canonical event dicts to ``POST /v1/events/raw``."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        queue: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.queue: asyncio.Queue[dict[str, Any]] = (
            queue if queue is not None else asyncio.Queue(maxsize=config.queue_max)
        )
        # Counters, exposed for tests and (eventually) for ops introspection.
        self.shipped_count = 0
        self.failed_count = 0
        self.dropped_count = 0

    async def enqueue(self, event: dict[str, Any]) -> None:
        """Add ``event`` to the ship queue. If the queue is full, drop the oldest."""
        try:
            self.queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass
        # Drop oldest, then enqueue. Counted as a dropped event so ops can
        # see when the agent is shedding load.
        try:
            _ = self.queue.get_nowait()
            self.dropped_count += 1
            log.warning(
                "ship queue full (%d), dropping oldest event (total dropped: %d)",
                self.config.queue_max,
                self.dropped_count,
            )
        except asyncio.QueueEmpty:
            pass
        self.queue.put_nowait(event)

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        """Main loop. Pulls events from the queue, batches them, ships them."""
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        headers = {
            "Authorization": f"Bearer {self.config.agent_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            base_url=self.config.api_url,
            headers=headers,
            timeout=timeout,
        ) as client:
            while True:
                if stop_event is not None and stop_event.is_set():
                    return

                batch = await self._collect_batch(stop_event)
                if not batch:
                    continue

                for event in batch:
                    ok = await self._ship_one(client, event, stop_event)
                    if ok:
                        self.shipped_count += 1
                    else:
                        self.failed_count += 1

    async def _collect_batch(
        self, stop_event: asyncio.Event | None
    ) -> list[dict[str, Any]]:
        """Drain up to ``batch_size`` events or up to ``flush_interval`` seconds."""
        batch: list[dict[str, Any]] = []
        deadline = (
            asyncio.get_event_loop().time() + self.config.flush_interval_seconds
        )
        while len(batch) < self.config.batch_size:
            if stop_event is not None and stop_event.is_set():
                break
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            batch.append(event)
        return batch

    async def _ship_one(
        self,
        client: httpx.AsyncClient,
        event: dict[str, Any],
        stop_event: asyncio.Event | None,
    ) -> bool:
        """Ship one event with retry/backoff. Return True iff backend returned 201."""
        backoff = _INITIAL_BACKOFF_SECONDS
        for attempt in range(1, _MAX_ATTEMPTS_PER_EVENT + 1):
            if stop_event is not None and stop_event.is_set():
                return False
            try:
                response = await client.post("/v1/events/raw", json=event)
            except httpx.RequestError as e:
                log.warning(
                    "network error shipping event (attempt %d/%d): %s",
                    attempt,
                    _MAX_ATTEMPTS_PER_EVENT,
                    e,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
                continue

            status = response.status_code
            if status == 201:
                return True

            if 400 <= status < 500:
                # Malformed payload — never retry. Log enough context to debug
                # without ever exposing the bearer token.
                log.error(
                    "backend rejected event (status=%d, kind=%s): %s — dropping",
                    status,
                    event.get("kind"),
                    response.text[:500],
                )
                return False

            # 5xx — backend is having a bad time; retry.
            log.warning(
                "backend %d on event ship (attempt %d/%d), retrying after %.1fs",
                status,
                attempt,
                _MAX_ATTEMPTS_PER_EVENT,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

        log.error(
            "max retries exhausted shipping event (kind=%s) — dropping",
            event.get("kind"),
        )
        return False
