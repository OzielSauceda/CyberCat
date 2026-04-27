from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.errors import ErrorEnvelope
from app.auth.dependencies import SystemUser, require_analyst, require_user, resolve_actor_id
from app.auth.models import User
from app.api.schemas.incidents import (
    ActionLogSummary,
    ActionSummary,
    AttackRef,
    DetectionRef,
    EntityRef,
    IncidentDetail,
    IncidentList,
    IncidentSummary,
    NoteIn,
    NoteRef,
    TimelineEvent,
    TransitionIn,
    TransitionOut,
    TransitionRef,
)
from app.db.models import (
    Action,
    ActionLog,
    Detection,
    Entity,
    Event,
    EventEntity,
    Incident,
    IncidentAttack,
    IncidentDetection,
    IncidentEntity,
    IncidentEvent,
    IncidentTransition,
    Note,
)
from app.db.session import get_db
from app.enums import IncidentStatus, Severity

_ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.new: {IncidentStatus.triaged, IncidentStatus.closed},
    IncidentStatus.triaged: {IncidentStatus.investigating, IncidentStatus.closed},
    IncidentStatus.investigating: {IncidentStatus.contained, IncidentStatus.resolved, IncidentStatus.closed},
    IncidentStatus.contained: {IncidentStatus.resolved, IncidentStatus.investigating, IncidentStatus.closed},
    IncidentStatus.resolved: {IncidentStatus.closed, IncidentStatus.investigating},
    IncidentStatus.closed: set(),
    IncidentStatus.reopened: {IncidentStatus.investigating},
}

_REASON_REQUIRED: set[IncidentStatus] = {
    IncidentStatus.contained,
    IncidentStatus.resolved,
    IncidentStatus.closed,
}

router = APIRouter(prefix="/incidents", tags=["incidents"])

_SEVERITY_ORDER = {
    Severity.info: 0,
    Severity.low: 1,
    Severity.medium: 2,
    Severity.high: 3,
    Severity.critical: 4,
}


def _encode_cursor(opened_at: datetime, incident_id: uuid.UUID) -> str:
    payload = {"opened_at": opened_at.isoformat(), "id": str(incident_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return datetime.fromisoformat(payload["opened_at"]), uuid.UUID(payload["id"])


@router.get("", response_model=IncidentList)
async def list_incidents(
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
    status: Annotated[str | None, Query()] = None,
    severity_gte: Annotated[str | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    opened_after: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> IncidentList:
    q = select(Incident).order_by(Incident.opened_at.desc(), Incident.id.desc())

    if status:
        statuses = [IncidentStatus(s.strip()) for s in status.split(",")]
        q = q.where(Incident.status.in_(statuses))

    if severity_gte:
        min_ord = _SEVERITY_ORDER[Severity(severity_gte)]
        allowed = [s for s, o in _SEVERITY_ORDER.items() if o >= min_ord]
        q = q.where(Incident.severity.in_(allowed))

    if opened_after:
        q = q.where(Incident.opened_at >= opened_after)

    if entity_id:
        q = q.where(
            Incident.id.in_(
                select(IncidentEntity.incident_id).where(
                    IncidentEntity.entity_id == entity_id
                )
            )
        )

    if cursor:
        cursor_opened_at, cursor_id = _decode_cursor(cursor)
        q = q.where(
            (Incident.opened_at < cursor_opened_at)
            | (
                (Incident.opened_at == cursor_opened_at)
                & (Incident.id < cursor_id)
            )
        )

    q = q.limit(limit + 1)
    result = await db.execute(q)
    incidents = list(result.scalars().all())

    next_cursor: str | None = None
    if len(incidents) > limit:
        incidents = incidents[:limit]
        last = incidents[-1]
        next_cursor = _encode_cursor(last.opened_at, last.id)

    items: list[IncidentSummary] = []
    for inc in incidents:
        entity_count = await db.scalar(
            select(func.count(IncidentEntity.entity_id)).where(
                IncidentEntity.incident_id == inc.id
            )
        ) or 0
        detection_count = await db.scalar(
            select(func.count(IncidentDetection.detection_id)).where(
                IncidentDetection.incident_id == inc.id
            )
        ) or 0
        event_count = await db.scalar(
            select(func.count(IncidentEvent.event_id)).where(
                IncidentEvent.incident_id == inc.id
            )
        ) or 0

        # primary user / host from incident_entities
        user_result = await db.execute(
            select(Entity.natural_key)
            .join(IncidentEntity, IncidentEntity.entity_id == Entity.id)
            .where(
                IncidentEntity.incident_id == inc.id,
                Entity.kind == "user",
            )
            .limit(1)
        )
        primary_user = user_result.scalar_one_or_none()

        host_result = await db.execute(
            select(Entity.natural_key)
            .join(IncidentEntity, IncidentEntity.entity_id == Entity.id)
            .where(
                IncidentEntity.incident_id == inc.id,
                Entity.kind == "host",
            )
            .limit(1)
        )
        primary_host = host_result.scalar_one_or_none()

        items.append(IncidentSummary(
            id=inc.id,
            title=inc.title,
            kind=inc.kind,
            status=inc.status,
            severity=inc.severity,
            confidence=inc.confidence,
            opened_at=inc.opened_at,
            updated_at=inc.updated_at,
            entity_count=entity_count,
            detection_count=detection_count,
            event_count=event_count,
            primary_user=primary_user,
            primary_host=primary_host,
        ))

    return IncidentList(items=items, next_cursor=next_cursor)


@router.get(
    "/{incident_id}",
    response_model=IncidentDetail,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
) -> IncidentDetail:
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Incident not found"}})

    # Entities
    ent_result = await db.execute(
        select(Entity, IncidentEntity.role)
        .join(IncidentEntity, IncidentEntity.entity_id == Entity.id)
        .where(IncidentEntity.incident_id == incident_id)
    )
    entities = [
        EntityRef(
            id=e.id,
            kind=e.kind,
            natural_key=e.natural_key,
            attrs=e.attrs,
            role_in_incident=str(role.value),
        )
        for e, role in ent_result.all()
    ]

    # Detections
    det_result = await db.execute(
        select(Detection)
        .join(IncidentDetection, IncidentDetection.detection_id == Detection.id)
        .where(IncidentDetection.incident_id == incident_id)
        .order_by(Detection.created_at)
    )
    detections = [
        DetectionRef(
            id=d.id,
            rule_id=d.rule_id,
            rule_source=d.rule_source.value,
            rule_version=d.rule_version,
            severity_hint=d.severity_hint,
            confidence_hint=d.confidence_hint,
            attack_tags=d.attack_tags,
            matched_fields=d.matched_fields,
            event_id=d.event_id,
            created_at=d.created_at,
        )
        for d in det_result.scalars().all()
    ]

    # Timeline events + their entity_ids
    ie_result = await db.execute(
        select(Event, IncidentEvent.role)
        .join(IncidentEvent, IncidentEvent.event_id == Event.id)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(Event.occurred_at)
    )
    timeline: list[TimelineEvent] = []
    for ev, ie_role in ie_result.all():
        ee_result = await db.execute(
            select(EventEntity.entity_id).where(EventEntity.event_id == ev.id)
        )
        entity_ids = list(ee_result.scalars().all())
        timeline.append(TimelineEvent(
            id=ev.id,
            occurred_at=ev.occurred_at,
            kind=ev.kind,
            source=ev.source.value,
            normalized=ev.normalized,
            role_in_incident=ie_role.value,
            entity_ids=entity_ids,
        ))

    # ATT&CK
    attack_result = await db.execute(
        select(IncidentAttack).where(IncidentAttack.incident_id == incident_id)
    )
    attack = [
        AttackRef(
            tactic=a.tactic,
            technique=a.technique,
            subtechnique=a.subtechnique,
            source=a.source.value,
        )
        for a in attack_result.scalars().all()
    ]

    # Actions + latest log
    action_result = await db.execute(
        select(Action)
        .where(Action.incident_id == incident_id)
        .order_by(Action.proposed_at)
    )
    actions: list[ActionSummary] = []
    for act in action_result.scalars().all():
        log_result = await db.execute(
            select(ActionLog)
            .where(ActionLog.action_id == act.id)
            .order_by(ActionLog.executed_at.desc())
            .limit(1)
        )
        last_log_row = log_result.scalar_one_or_none()
        last_log = (
            ActionLogSummary(
                executed_at=last_log_row.executed_at,
                executed_by=last_log_row.executed_by,
                result=last_log_row.result.value,
                reason=last_log_row.reason,
                reversal_info=last_log_row.reversal_info,
                actor_user_id=last_log_row.actor_user_id,
            )
            if last_log_row
            else None
        )
        actions.append(ActionSummary(
            id=act.id,
            kind=act.kind.value,
            classification=act.classification.value,
            classification_reason=act.classification_reason,
            status=act.status.value,
            params=act.params,
            proposed_by=act.proposed_by.value,
            proposed_at=act.proposed_at,
            last_log=last_log,
        ))

    # Transitions
    trans_result = await db.execute(
        select(IncidentTransition)
        .where(IncidentTransition.incident_id == incident_id)
        .order_by(IncidentTransition.at)
    )
    transitions = [
        TransitionRef(
            from_status=t.from_status,
            to_status=t.to_status,
            actor=t.actor,
            reason=t.reason,
            at=t.at,
            actor_user_id=t.actor_user_id,
        )
        for t in trans_result.scalars().all()
    ]

    # Notes
    note_result = await db.execute(
        select(Note)
        .where(Note.incident_id == incident_id)
        .order_by(Note.created_at)
    )
    notes = [
        NoteRef(id=n.id, body=n.body, author=n.author, created_at=n.created_at, actor_user_id=n.actor_user_id)
        for n in note_result.scalars().all()
    ]

    return IncidentDetail(
        id=inc.id,
        title=inc.title,
        kind=inc.kind,
        status=inc.status,
        severity=inc.severity,
        confidence=inc.confidence,
        rationale=inc.rationale,
        opened_at=inc.opened_at,
        updated_at=inc.updated_at,
        closed_at=inc.closed_at,
        correlator_rule=inc.correlator_rule,
        correlator_version=inc.correlator_version,
        entities=entities,
        detections=detections,
        timeline=timeline,
        attack=attack,
        actions=actions,
        transitions=transitions,
        notes=notes,
    )


@router.post(
    "/{incident_id}/transitions",
    response_model=TransitionOut,
    status_code=201,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def transition_incident(
    incident_id: uuid.UUID,
    body: TransitionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> TransitionOut:
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "incident_not_found", "message": "Incident not found"}},
        )

    allowed = _ALLOWED_TRANSITIONS.get(inc.status, set())
    if body.to_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "invalid_transition",
                    "message": f"Cannot transition from {inc.status.value!r} to {body.to_status.value!r}",
                }
            },
        )

    if body.to_status in _REASON_REQUIRED and not (body.reason and body.reason.strip()):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "reason_required",
                    "message": f"A reason is required when transitioning to {body.to_status.value!r}",
                }
            },
        )

    actor_id = await resolve_actor_id(current_user, db)
    from_status = inc.status
    now = datetime.now(timezone.utc)
    inc.status = body.to_status
    inc.updated_at = now
    if body.to_status == IncidentStatus.closed:
        inc.closed_at = now

    transition = IncidentTransition(
        incident_id=inc.id,
        from_status=from_status,
        to_status=body.to_status,
        actor=current_user.email,
        actor_user_id=actor_id,
        reason=body.reason,
        at=now,
    )
    db.add(transition)
    await db.commit()

    from app.streaming.publisher import publish
    await publish("incident.transitioned", {
        "incident_id": str(inc.id),
        "from_status": from_status.value,
        "to_status": body.to_status.value,
    })

    return TransitionOut(
        incident_id=inc.id,
        from_status=from_status,
        to_status=body.to_status,
        at=now,
    )


@router.post(
    "/{incident_id}/notes",
    response_model=NoteRef,
    status_code=201,
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def add_note(
    incident_id: uuid.UUID,
    body: NoteIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> NoteRef:
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "incident_not_found", "message": "Incident not found"}},
        )

    stripped = body.body.strip()
    if len(stripped) < 1:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "body_too_short", "message": "Note body must not be empty"}},
        )
    if len(stripped) > 4000:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "body_too_long", "message": "Note body must not exceed 4000 characters"}},
        )

    actor_id = await resolve_actor_id(current_user, db)
    note = Note(
        incident_id=incident_id,
        body=stripped,
        author=current_user.email,
        actor_user_id=actor_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return NoteRef(id=note.id, body=note.body, author=note.author, created_at=note.created_at, actor_user_id=note.actor_user_id)
