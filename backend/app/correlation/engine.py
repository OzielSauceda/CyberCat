from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Detection, Event

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CorrelatorFn = Callable[
    [Detection, Event, AsyncSession, aioredis.Redis],
    Awaitable[uuid.UUID | None],
]

_CORRELATORS: list[CorrelatorFn] = []


def register(fn: CorrelatorFn) -> CorrelatorFn:
    _CORRELATORS.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

async def run_correlators(
    detections: list[Detection],
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> uuid.UUID | None:
    """Run correlators against each fired detection. Return first incident ID created/touched."""
    for detection in detections:
        for correlator in _CORRELATORS:
            incident_id = await correlator(detection, event, db, redis)
            if incident_id is not None:
                return incident_id
    return None
