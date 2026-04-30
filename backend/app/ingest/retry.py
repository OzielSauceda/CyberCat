"""Phase 19 — single-retry wrapper for transient DB connection drops on the ingest path.

When a long-running ingest loop (e.g. the Wazuh poller) holds a session and the
underlying Postgres connection is invalidated mid-batch, we want one quick retry
with a fresh session before counting it as a failure. Other errors propagate
unchanged so they're visible to the caller and can feed the circuit-breaker.

Read paths intentionally don't use this — they should fail fast and let the
client retry or fall through to a 503.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRY_DELAY_SEC = 0.1


async def with_ingest_retry(
    op: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    """Run `op(session)` once; on connection-invalidated DBAPIError, retry once.

    `op` is invoked with a fresh `AsyncSession` each attempt. The session is
    closed after `op` returns (success or failure).
    """
    try:
        async with AsyncSessionLocal() as session:
            return await op(session)
    except DBAPIError as exc:
        if not exc.connection_invalidated:
            raise
        logger.warning(
            "ingest db connection invalidated; retrying once after %.0fms",
            _RETRY_DELAY_SEC * 1000,
        )
        await asyncio.sleep(_RETRY_DELAY_SEC)
        async with AsyncSessionLocal() as session:
            return await op(session)
