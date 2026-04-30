from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.correlation.engine import register
from app.db.models import (
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
)
from app.enums import (
    AttackSource,
    EntityKind,
    IncidentEntityRole,
    IncidentEventRole,
    IncidentKind,
    IncidentStatus,
    Severity,
)

log = logging.getLogger(__name__)

_TRIGGER_PREFIXES = ("py.process.", "sigma-proc_creation_", "sigma-proc-creation-")
_LOOKBACK_MINUTES = 30
_CLOSED_STATUSES = {IncidentStatus.resolved, IncidentStatus.closed}


def _is_endpoint_detection(rule_id: str) -> bool:
    return any(rule_id.startswith(p) for p in _TRIGGER_PREFIXES)


@register
async def identity_endpoint_chain(
    detection: Detection,
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> uuid.UUID | None:
    if not _is_endpoint_detection(detection.rule_id):
        return None

    # Resolve user and host from event entity links (set by entity_extractor)
    ee_result = await db.execute(
        select(Entity, EventEntity.role)
        .join(EventEntity, EventEntity.entity_id == Entity.id)
        .where(EventEntity.event_id == event.id)
    )
    user_entity: Entity | None = None
    host_entity: Entity | None = None
    for entity, _role in ee_result.all():
        if entity.kind == EntityKind.user:
            user_entity = entity
        elif entity.kind == EntityKind.host:
            host_entity = entity

    # Fall back: look up user entity by natural key from normalized data
    if user_entity is None:
        user_key_raw = event.normalized.get("user", "")
        if user_key_raw:
            ue_result = await db.execute(
                select(Entity).where(
                    Entity.kind == EntityKind.user,
                    Entity.natural_key == user_key_raw.lower(),
                )
            )
            user_entity = ue_result.scalar_one_or_none()

    if user_entity is None:
        return None

    host_key = host_entity.natural_key if host_entity else event.normalized.get("host", "")
    if not host_key:
        return None

    # Find an open identity_compromise incident for this user within the lookback window.
    window_start = datetime.now(UTC) - timedelta(minutes=_LOOKBACK_MINUTES)

    inc_result = await db.execute(
        select(Incident)
        .where(
            Incident.kind == IncidentKind.identity_compromise,
            Incident.status.not_in(list(_CLOSED_STATUSES)),
            Incident.opened_at >= window_start,
            Incident.id.in_(
                select(IncidentEntity.incident_id).where(
                    IncidentEntity.entity_id == user_entity.id
                )
            ),
        )
        .order_by(Incident.opened_at.desc())
    )
    identity_incident = inc_result.scalars().first()

    if identity_incident is None:
        return None

    # Dedup: one chain incident per user+host per hour bucket
    hour_bucket = event.occurred_at.strftime("%Y%m%d%H")
    dedupe_key = f"identity_endpoint_chain:{user_entity.natural_key}:{host_key}:{hour_bucket}"

    existing = await db.execute(
        select(Incident.id).where(Incident.dedupe_key == dedupe_key)
    )
    existing_id = existing.scalar_one_or_none()
    if existing_id is not None:
        return existing_id

    # Collect auth event IDs from the identity incident to link as supporting context
    ie_result = await db.execute(
        select(IncidentEvent.event_id).where(
            IncidentEvent.incident_id == identity_incident.id,
            IncidentEvent.role.in_([IncidentEventRole.trigger, IncidentEventRole.supporting]),
        )
    )
    auth_event_ids: list[uuid.UUID] = list(ie_result.scalars().all())

    rationale = (
        f"Process signal {detection.rule_id!r} observed on host {host_key!r} for user "
        f"{user_entity.natural_key!r}, who has an open identity compromise incident "
        f"(id={identity_incident.id}) opened within the last {_LOOKBACK_MINUTES} minutes. "
        f"Cross-layer correlation: successful credential compromise followed by endpoint "
        f"execution activity is consistent with post-authentication lateral movement or "
        f"hands-on-keyboard intrusion."
    )

    summary = (
        f"{user_entity.natural_key} just had a suspicious sign-in, and now their "
        f"account is running unusual programs on {host_key}. This is the strongest "
        f"sign yet that someone else has the account."
    )

    incident = Incident(
        id=uuid.uuid4(),
        title=f"Identity + endpoint compromise chain: {user_entity.natural_key} @ {host_key}",
        kind=IncidentKind.identity_endpoint_chain,
        status=IncidentStatus.new,
        severity=Severity.high,
        confidence=Decimal("0.85"),
        rationale=rationale,
        summary=summary,
        correlator_version="1.0.0",
        correlator_rule="identity_endpoint_chain",
        dedupe_key=dedupe_key,
    )
    db.add(incident)
    await db.flush()

    # Trigger: the process event that fired this correlator
    db.add(IncidentEvent(
        incident_id=incident.id,
        event_id=event.id,
        role=IncidentEventRole.trigger,
    ))

    # Supporting: auth events from the matched identity incident
    for auth_event_id in auth_event_ids:
        db.add(IncidentEvent(
            incident_id=incident.id,
            event_id=auth_event_id,
            role=IncidentEventRole.supporting,
        ))

    # Detection that triggered this correlator
    db.add(IncidentDetection(incident_id=incident.id, detection_id=detection.id))

    # Entities: user + host
    db.add(IncidentEntity(
        incident_id=incident.id,
        entity_id=user_entity.id,
        role=IncidentEntityRole.user,
    ))
    if host_entity is not None:
        db.add(IncidentEntity(
            incident_id=incident.id,
            entity_id=host_entity.id,
            role=IncidentEntityRole.host,
        ))

    # ATT&CK: union of identity (credential-access) + endpoint (execution)
    for tactic, technique, subtechnique in [
        ("credential-access", "T1110", None),
        ("credential-access", "T1078", None),
        ("execution", "T1059", None),
        ("execution", "T1059", "T1059.001"),
    ]:
        db.add(IncidentAttack(
            incident_id=incident.id,
            tactic=tactic,
            technique=technique,
            subtechnique=subtechnique,
            source=AttackSource.correlator_inferred,
        ))

    # Initial transition: null → new
    db.add(IncidentTransition(
        incident_id=incident.id,
        from_status=None,
        to_status=IncidentStatus.new,
        actor="system:correlator",
    ))

    log.info(
        "identity_endpoint_chain: created incident %s (user=%s host=%s identity_incident=%s)",
        incident.id,
        user_entity.natural_key,
        host_key,
        identity_incident.id,
    )

    return incident.id
