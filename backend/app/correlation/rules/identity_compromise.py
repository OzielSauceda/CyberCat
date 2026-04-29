from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.correlation.engine import register
from app.db.models import (
    Detection,
    Entity,
    Event,
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

_TRIGGER_RULE = "py.auth.anomalous_source_success"
_BURST_RULE = "py.auth.failed_burst"
_FAILURE_LOOKBACK_MIN = 5


@register
async def identity_compromise(
    detection: Detection,
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> uuid.UUID | None:
    if detection.rule_id != _TRIGGER_RULE:
        return None

    user: str = event.normalized.get("user", "")
    source_ip: str = event.normalized.get("source_ip", "")
    if not user or not source_ip:
        return None

    # One incident per user per hour bucket
    hour_bucket = event.occurred_at.strftime("%Y%m%d%H")
    dedupe_key = f"identity_compromise:{user}:{hour_bucket}"

    existing = await db.execute(
        select(Incident.id).where(Incident.dedupe_key == dedupe_key)
    )
    existing_id = existing.scalar_one_or_none()
    if existing_id is not None:
        return existing_id

    # Find recent auth.failed events for this user from same source
    window_start = event.occurred_at - timedelta(minutes=_FAILURE_LOOKBACK_MIN)
    failed_result = await db.execute(
        select(Event)
        .where(
            Event.kind == "auth.failed",
            Event.occurred_at >= window_start,
            Event.occurred_at <= event.occurred_at,
            Event.normalized["user"].astext == user,
            Event.normalized["source_ip"].astext == source_ip,
        )
        .order_by(Event.occurred_at)
    )
    failed_events = list(failed_result.scalars().all())
    failure_count = len(failed_events)

    # Find the burst detection if one fired for this user
    burst_detection: Detection | None = None
    if failed_events:
        burst_result = await db.execute(
            select(Detection).where(
                Detection.rule_id == _BURST_RULE,
                Detection.event_id.in_([e.id for e in failed_events]),
            )
        )
        burst_detection = burst_result.scalar_one_or_none()

    rationale = (
        f"{failure_count} failed authentication{'s' if failure_count != 1 else ''} "
        f"for {user} from {source_ip} within {_FAILURE_LOOKBACK_MIN} minutes, "
        f"followed by a successful authentication from the same previously-unseen source. "
        f"Pattern consistent with successful credential guessing or password spraying."
    )

    if failure_count > 0:
        summary = (
            f"{user} signed in from a new address ({source_ip}) right after "
            f"{failure_count} failed attempt{'s' if failure_count != 1 else ''}. "
            f"This often means someone guessed the password."
        )
    else:
        summary = (
            f"{user} signed in from a new address ({source_ip}) that hasn't been "
            f"seen before. Worth checking whether this is the real person."
        )

    incident = Incident(
        id=uuid.uuid4(),
        title=f"Suspicious sign-in for {user} from new source {source_ip}",
        kind=IncidentKind.identity_compromise,
        status=IncidentStatus.new,
        severity=Severity.high,
        confidence=Decimal("0.80"),
        rationale=rationale,
        summary=summary,
        correlator_version="1.0.0",
        correlator_rule="identity_compromise",
        dedupe_key=dedupe_key,
    )
    db.add(incident)
    await db.flush()

    # Link trigger event
    db.add(IncidentEvent(
        incident_id=incident.id,
        event_id=event.id,
        role=IncidentEventRole.trigger,
    ))
    # Link supporting events
    for fe in failed_events:
        db.add(IncidentEvent(
            incident_id=incident.id,
            event_id=fe.id,
            role=IncidentEventRole.supporting,
        ))

    # Link detections
    db.add(IncidentDetection(incident_id=incident.id, detection_id=detection.id))
    if burst_detection is not None:
        db.add(IncidentDetection(
            incident_id=incident.id,
            detection_id=burst_detection.id,
        ))

    # Link ATT&CK techniques
    for tactic, technique, subtechnique in [
        ("credential-access", "T1110", None),
        ("credential-access", "T1110", "T1110.003"),
        ("initial-access", "T1078", None),
    ]:
        db.add(IncidentAttack(
            incident_id=incident.id,
            tactic=tactic,
            technique=technique,
            subtechnique=subtechnique,
            source=AttackSource.rule_derived,
        ))

    # Link entities (user + source_ip) if they exist
    for entity_kind, natural_key, role in [
        (EntityKind.user, user, IncidentEntityRole.user),
        (EntityKind.ip, source_ip, IncidentEntityRole.source_ip),
    ]:
        entity_result = await db.execute(
            select(Entity.id).where(
                Entity.kind == entity_kind,
                Entity.natural_key == natural_key,
            )
        )
        entity_id = entity_result.scalar_one_or_none()
        if entity_id is not None:
            db.add(IncidentEntity(
                incident_id=incident.id,
                entity_id=entity_id,
                role=role,
            ))

    # Open transition: null → new
    db.add(IncidentTransition(
        incident_id=incident.id,
        from_status=None,
        to_status=IncidentStatus.new,
        actor="system",
    ))

    return incident.id
