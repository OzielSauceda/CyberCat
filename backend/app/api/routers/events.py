from __future__ import annotations

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.events import EventList, EventSummary, RawEventAccepted, RawEventIn
from app.auth.dependencies import SystemUser, require_analyst, require_user
from app.auth.models import User
from app.db.models import Event
from app.db.redis import get_redis
from app.db.session import get_db
from app.enums import EventSource
from app.ingest.normalizer import KNOWN_KINDS, validate_normalized
from app.ingest.pipeline import ingest_normalized_event
from app.ingest.retry import with_ingest_retry

router = APIRouter(prefix="/events", tags=["ingest"])


@router.get("", response_model=EventList)
async def list_events(
    source: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
) -> EventList:
    stmt = select(Event).order_by(Event.occurred_at.desc())
    if source is not None:
        stmt = stmt.where(Event.source == source)
    if kind is not None:
        stmt = stmt.where(Event.kind == kind)
    stmt = stmt.limit(limit)
    rows = await db.execute(stmt)
    events = rows.scalars().all()
    count_stmt = select(func.count()).select_from(Event)
    if source is not None:
        count_stmt = count_stmt.where(Event.source == source)
    if kind is not None:
        count_stmt = count_stmt.where(Event.kind == kind)
    total = (await db.execute(count_stmt)).scalar_one()
    return EventList(
        items=[
            EventSummary(
                id=e.id,
                occurred_at=e.occurred_at,
                source=e.source.value,
                kind=e.kind,
                dedupe_key=e.dedupe_key,
            )
            for e in events
        ],
        total=total,
    )


@router.post("/raw", response_model=RawEventAccepted, status_code=201)
async def ingest_raw_event(
    body: RawEventIn,
    redis: aioredis.Redis = Depends(get_redis),
    _user: User | SystemUser = Depends(require_analyst),
) -> RawEventAccepted:
    if body.kind not in KNOWN_KINDS:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_kind", "message": f"Unknown event kind: {body.kind!r}"}},
        )

    missing = validate_normalized(body.kind, body.normalized)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "normalized_shape_mismatch",
                    "message": f"Missing required fields in normalized: {missing}",
                    "details": {"missing_fields": missing},
                }
            },
        )

    async def _do_ingest(session: AsyncSession):
        return await ingest_normalized_event(
            session,
            redis,
            source=EventSource(body.source),
            kind=body.kind,
            occurred_at=body.occurred_at,
            raw=body.raw,
            normalized=body.normalized,
            dedupe_key=body.dedupe_key,
        )

    result = await with_ingest_retry(_do_ingest)

    return RawEventAccepted(
        event_id=result.event_id,
        dedup_hit=result.dedup_hit,
        detections_fired=result.detection_ids,
        incident_touched=result.incident_touched,
    )
