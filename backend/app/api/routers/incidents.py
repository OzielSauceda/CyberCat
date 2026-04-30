from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.errors import ErrorEnvelope
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
    RecommendedActionOut,
    TimelineEvent,
    TransitionIn,
    TransitionOut,
    TransitionRef,
)
from app.auth.dependencies import SystemUser, require_analyst, require_user, resolve_actor_id
from app.auth.models import User
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
from app.enums import IncidentEntityRole, IncidentStatus, Severity
from app.response.recommendations import recommend_for_incident

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

    # Phase 19: batched aggregate fetches replace the previous per-incident
    # N+1 (5 queries × N incidents → 250 queries on a 50-item page).
    incident_ids = [inc.id for inc in incidents]
    entity_counts: dict[uuid.UUID, int] = {}
    detection_counts: dict[uuid.UUID, int] = {}
    event_counts: dict[uuid.UUID, int] = {}
    primary_users: dict[uuid.UUID, str | None] = {}
    primary_hosts: dict[uuid.UUID, str | None] = {}

    if incident_ids:
        ent_rows = await db.execute(
            select(IncidentEntity.incident_id, func.count(IncidentEntity.entity_id))
            .where(IncidentEntity.incident_id.in_(incident_ids))
            .group_by(IncidentEntity.incident_id)
        )
        entity_counts = {row[0]: row[1] for row in ent_rows.all()}

        det_rows = await db.execute(
            select(IncidentDetection.incident_id, func.count(IncidentDetection.detection_id))
            .where(IncidentDetection.incident_id.in_(incident_ids))
            .group_by(IncidentDetection.incident_id)
        )
        detection_counts = {row[0]: row[1] for row in det_rows.all()}

        evt_rows = await db.execute(
            select(IncidentEvent.incident_id, func.count(IncidentEvent.event_id))
            .where(IncidentEvent.incident_id.in_(incident_ids))
            .group_by(IncidentEvent.incident_id)
        )
        event_counts = {row[0]: row[1] for row in evt_rows.all()}

        # One query for primary user + host per incident; pick the
        # first natural_key per (incident_id, kind) pair.
        ent_link_rows = await db.execute(
            select(IncidentEntity.incident_id, Entity.kind, Entity.natural_key)
            .join(Entity, IncidentEntity.entity_id == Entity.id)
            .where(
                IncidentEntity.incident_id.in_(incident_ids),
                Entity.kind.in_(["user", "host"]),
            )
        )
        for inc_id, kind, natural_key in ent_link_rows.all():
            if kind == "user" and inc_id not in primary_users:
                primary_users[inc_id] = natural_key
            elif kind == "host" and inc_id not in primary_hosts:
                primary_hosts[inc_id] = natural_key

    items: list[IncidentSummary] = []
    for inc in incidents:
        items.append(IncidentSummary(
            id=inc.id,
            title=inc.title,
            kind=inc.kind,
            status=inc.status,
            severity=inc.severity,
            confidence=inc.confidence,
            summary=inc.summary,
            opened_at=inc.opened_at,
            updated_at=inc.updated_at,
            entity_count=entity_counts.get(inc.id, 0),
            detection_count=detection_counts.get(inc.id, 0),
            event_count=event_counts.get(inc.id, 0),
            primary_user=primary_users.get(inc.id),
            primary_host=primary_hosts.get(inc.id),
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
        summary=inc.summary,
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
    now = datetime.now(UTC)
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
        created_at=datetime.now(UTC),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return NoteRef(id=note.id, body=note.body, author=note.author, created_at=note.created_at, actor_user_id=note.actor_user_id)


@router.get(
    "/{incident_id}/recommended-actions",
    response_model=list[RecommendedActionOut],
    responses={404: {"model": ErrorEnvelope}},
)
async def get_recommended_actions(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
) -> list[RecommendedActionOut]:
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Incident not found"}},
        )

    ent_result = await db.execute(
        select(Entity, IncidentEntity.role)
        .join(IncidentEntity, IncidentEntity.entity_id == Entity.id)
        .where(IncidentEntity.incident_id == incident_id)
    )
    entities = [(e, IncidentEntityRole(role.value)) for e, role in ent_result.all()]

    attack_result = await db.execute(
        select(IncidentAttack).where(IncidentAttack.incident_id == incident_id)
    )
    attack = list(attack_result.scalars().all())

    action_result = await db.execute(
        select(Action).where(Action.incident_id == incident_id)
    )
    actions = list(action_result.scalars().all())

    recs = recommend_for_incident(inc, entities, attack, actions)

    return [
        RecommendedActionOut(
            kind=r.kind,
            params=r.params,
            summary=r.summary,
            rationale=r.rationale,
            classification=r.classification,
            classification_reason=r.classification_reason,
            priority=r.priority,
            target_summary=r.target_summary,
        )
        for r in recs
    ]
