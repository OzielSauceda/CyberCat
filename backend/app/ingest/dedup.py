from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.enums import EventSource


async def find_duplicate(
    db: AsyncSession,
    source: EventSource,
    dedupe_key: str,
) -> uuid.UUID | None:
    """Return the existing event_id if this (source, dedupe_key) pair already exists."""
    result = await db.execute(
        select(Event.id).where(
            Event.source == source,
            Event.dedupe_key == dedupe_key,
        )
    )
    row = result.scalar_one_or_none()
    return row
