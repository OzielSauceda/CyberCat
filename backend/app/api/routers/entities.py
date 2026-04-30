from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.entities import EntityDetail, EntityIncidentSummary, EntityTimelineEvent
from app.api.schemas.errors import ErrorEnvelope
from app.db.models import Entity, Event, EventEntity, Incident, IncidentEntity
from app.db.session import get_db
from app.enums import EntityKind

router = APIRouter(prefix="/entities", tags=["entities"])

_RECENT_EVENTS_LIMIT = 50
_RELATED_INCIDENTS_LIMIT = 50


async def _build_entity_detail(entity: Entity, db: AsyncSession) -> EntityDetail:
    # Recent events via event_entities junction, newest first
    ev_result = await db.execute(
        select(Event)
        .join(EventEntity, EventEntity.event_id == Event.id)
        .where(EventEntity.entity_id == entity.id)
        .order_by(Event.occurred_at.desc())
        .limit(_RECENT_EVENTS_LIMIT)
    )
    recent_events = [
        EntityTimelineEvent(
            id=ev.id,
            occurred_at=ev.occurred_at,
            kind=ev.kind,
            normalized=ev.normalized,
        )
        for ev in ev_result.scalars().all()
    ]

    # Related incidents via incident_entities junction, newest first
    inc_result = await db.execute(
        select(Incident)
        .join(IncidentEntity, IncidentEntity.incident_id == Incident.id)
        .where(IncidentEntity.entity_id == entity.id)
        .order_by(Incident.opened_at.desc())
        .limit(_RELATED_INCIDENTS_LIMIT)
    )
    related_incidents = [
        EntityIncidentSummary(
            id=inc.id,
            title=inc.title,
            kind=inc.kind,
            status=inc.status,
            severity=inc.severity,
            confidence=inc.confidence,
            opened_at=inc.opened_at,
            updated_at=inc.updated_at,
        )
        for inc in inc_result.scalars().all()
    ]

    return EntityDetail(
        id=entity.id,
        kind=entity.kind,
        natural_key=entity.natural_key,
        attrs=entity.attrs,
        first_seen=entity.first_seen,
        last_seen=entity.last_seen,
        recent_events=recent_events,
        related_incidents=related_incidents,
    )


@router.get("/{entity_id}", response_model=EntityDetail, responses={404: {"model": ErrorEnvelope}})
async def get_entity(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EntityDetail:
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "entity_not_found", "message": "Entity not found"}},
        )
    return await _build_entity_detail(entity, db)


@router.get("", response_model=EntityDetail, responses={404: {"model": ErrorEnvelope}})
async def lookup_entity(
    kind: Annotated[EntityKind, Query()],
    natural_key: Annotated[str, Query()],
    db: AsyncSession = Depends(get_db),
) -> EntityDetail:
    result = await db.execute(
        select(Entity).where(
            Entity.kind == kind,
            Entity.natural_key == natural_key.lower(),
        )
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "entity_not_found", "message": "Entity not found"}},
        )
    return await _build_entity_detail(entity, db)
