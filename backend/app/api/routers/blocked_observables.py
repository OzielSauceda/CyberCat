from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlockedObservable
from app.db.session import get_db

router = APIRouter(prefix="/blocked-observables", tags=["blocked-observables"])


class BlockedObservableOut(BaseModel):
    id: uuid.UUID
    kind: str
    value: str
    blocked_at: datetime
    active: bool


class BlockedObservableList(BaseModel):
    items: list[BlockedObservableOut]


def _to_out(bo: BlockedObservable) -> BlockedObservableOut:
    return BlockedObservableOut(
        id=bo.id,
        kind=bo.kind.value,
        value=bo.value,
        blocked_at=bo.blocked_at,
        active=bo.active,
    )


@router.get("", response_model=BlockedObservableList)
async def list_blocked_observables(
    db: AsyncSession = Depends(get_db),
    active: Annotated[bool | None, Query()] = None,
    value: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> BlockedObservableList:
    q = select(BlockedObservable).order_by(BlockedObservable.blocked_at.desc())
    if active is not None:
        q = q.where(BlockedObservable.active == active)
    if value is not None:
        q = q.where(BlockedObservable.value == value)
    q = q.limit(limit)
    result = await db.execute(q)
    items = [_to_out(bo) for bo in result.scalars().all()]
    return BlockedObservableList(items=items)
