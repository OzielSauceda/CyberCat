from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import SystemUser, require_analyst, require_user, resolve_actor_id
from app.auth.models import User
from app.db.models import EvidenceRequest
from app.db.session import get_db
from app.enums import EvidenceStatus
from app.streaming.publisher import publish

router = APIRouter(prefix="/evidence-requests", tags=["evidence-requests"])


class EvidenceRequestOut(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    target_host_entity_id: uuid.UUID | None
    kind: str
    status: str
    requested_at: datetime
    collected_at: datetime | None
    payload_url: str | None


class EvidenceRequestList(BaseModel):
    items: list[EvidenceRequestOut]


def _to_out(er: EvidenceRequest) -> EvidenceRequestOut:
    return EvidenceRequestOut(
        id=er.id,
        incident_id=er.incident_id,
        target_host_entity_id=er.target_host_entity_id,
        kind=er.kind.value,
        status=er.status.value,
        requested_at=er.requested_at,
        collected_at=er.collected_at,
        payload_url=er.payload_url,
    )


@router.get("", response_model=EvidenceRequestList)
async def list_evidence_requests(
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
    incident_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EvidenceRequestList:
    q = select(EvidenceRequest).order_by(EvidenceRequest.requested_at.desc())
    if incident_id:
        q = q.where(EvidenceRequest.incident_id == incident_id)
    if status:
        q = q.where(EvidenceRequest.status == EvidenceStatus(status))
    q = q.limit(limit)
    result = await db.execute(q)
    items = [_to_out(er) for er in result.scalars().all()]
    return EvidenceRequestList(items=items)


@router.post("/{request_id}/collect", response_model=EvidenceRequestOut)
async def collect_evidence_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> EvidenceRequestOut:
    er = await db.get(EvidenceRequest, request_id)
    if er is None:
        raise HTTPException(status_code=404, detail="Evidence request not found")
    if er.status != EvidenceStatus.open:
        raise HTTPException(status_code=409, detail=f"Request is already {er.status.value}")
    actor_id = await resolve_actor_id(current_user, db)
    er.status = EvidenceStatus.collected
    er.collected_at = datetime.now(UTC)
    er.collected_by_user_id = actor_id
    await db.commit()
    await publish("evidence.collected", {
        "evidence_request_id": str(er.id),
        "incident_id": str(er.incident_id),
    })
    return _to_out(er)


@router.post("/{request_id}/dismiss", response_model=EvidenceRequestOut)
async def dismiss_evidence_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> EvidenceRequestOut:
    er = await db.get(EvidenceRequest, request_id)
    if er is None:
        raise HTTPException(status_code=404, detail="Evidence request not found")
    if er.status != EvidenceStatus.open:
        raise HTTPException(status_code=409, detail=f"Request is already {er.status.value}")
    actor_id = await resolve_actor_id(current_user, db)
    er.status = EvidenceStatus.dismissed
    er.dismissed_by_user_id = actor_id
    await db.commit()
    await publish("evidence.dismissed", {
        "evidence_request_id": str(er.id),
        "incident_id": str(er.incident_id),
    })
    return _to_out(er)
