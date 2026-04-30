from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.detections import DetectionItem, DetectionList
from app.db.models import Detection, IncidentDetection
from app.db.session import get_db
from app.enums import DetectionRuleSource

router = APIRouter(prefix="/detections", tags=["detections"])


def _encode_cursor(created_at: datetime, detection_id: uuid.UUID) -> str:
    payload = {"created_at": created_at.isoformat(), "id": str(detection_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])


@router.get("", response_model=DetectionList)
async def list_detections(
    db: AsyncSession = Depends(get_db),
    incident_id: Annotated[uuid.UUID | None, Query()] = None,
    rule_id: Annotated[str | None, Query()] = None,
    rule_source: Annotated[DetectionRuleSource | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> DetectionList:
    q = select(Detection).order_by(Detection.created_at.desc(), Detection.id.desc())

    if incident_id:
        q = q.where(
            Detection.id.in_(
                select(IncidentDetection.detection_id).where(
                    IncidentDetection.incident_id == incident_id
                )
            )
        )

    if rule_id:
        q = q.where(Detection.rule_id == rule_id)

    if rule_source:
        q = q.where(Detection.rule_source == rule_source)

    if since:
        q = q.where(Detection.created_at >= since)

    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        q = q.where(
            (Detection.created_at < cursor_created_at)
            | (
                (Detection.created_at == cursor_created_at)
                & (Detection.id < cursor_id)
            )
        )

    q = q.limit(limit + 1)
    result = await db.execute(q)
    detections = list(result.scalars().all())

    next_cursor: str | None = None
    if len(detections) > limit:
        detections = detections[:limit]
        last = detections[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    # Phase 19: batched incident_id lookup replaces the previous per-detection
    # query (1 query × N detections → up to 200 queries on a max page).
    detection_ids = [d.id for d in detections]
    incident_link: dict[uuid.UUID, uuid.UUID] = {}
    if detection_ids:
        link_rows = await db.execute(
            select(IncidentDetection.detection_id, IncidentDetection.incident_id)
            .where(IncidentDetection.detection_id.in_(detection_ids))
        )
        for det_id, inc_id in link_rows.all():
            # First-write wins; a detection may belong to multiple incidents but
            # the API has historically surfaced one. Preserve that contract.
            incident_link.setdefault(det_id, inc_id)

    items: list[DetectionItem] = []
    for d in detections:
        items.append(DetectionItem(
            id=d.id,
            rule_id=d.rule_id,
            rule_source=d.rule_source.value,
            rule_version=d.rule_version,
            severity_hint=d.severity_hint,
            confidence_hint=d.confidence_hint,
            attack_tags=d.attack_tags,
            matched_fields=d.matched_fields,
            event_id=d.event_id,
            incident_id=incident_link.get(d.id),
            created_at=d.created_at,
        ))

    return DetectionList(items=items, next_cursor=next_cursor)
