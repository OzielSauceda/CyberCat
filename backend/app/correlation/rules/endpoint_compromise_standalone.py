from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from datetime import datetime, timezone

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
_DEDUP_TTL = 7200  # 2 hours


def _is_endpoint_detection(rule_id: str) -> bool:
    return any(rule_id.startswith(p) for p in _TRIGGER_PREFIXES)


@register
async def endpoint_compromise_standalone(
    detection: Detection,
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> uuid.UUID | None:
    if not _is_endpoint_detection(detection.rule_id):
        return None

    # Resolve host entity from event links
    ee_result = await db.execute(
        select(Entity, EventEntity.role)
        .join(EventEntity, EventEntity.entity_id == Entity.id)
        .where(EventEntity.event_id == event.id)
    )
    host_entity: Entity | None = None
    for entity, _role in ee_result.all():
        if entity.kind == EntityKind.host:
            host_entity = entity
            break

    if host_entity is None:
        # Fall back to host field in normalized data
        host_key = event.normalized.get("host", "")
        if not host_key:
            log.info(
                "endpoint_compromise_standalone: event %s has no host entity — skipping",
                event.id,
            )
            return None
        host_natural_key = host_key
    else:
        host_natural_key = host_entity.natural_key

    # Redis hour-bucket dedup — SETNX; if already set, a standalone incident opened this hour
    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    dedup_redis_key = f"endpoint_compromise:{host_natural_key}:{hour_bucket}"
    was_set = await redis.set(dedup_redis_key, "1", nx=True, ex=_DEDUP_TTL)
    if not was_set:
        log.info(
            "endpoint_compromise_standalone: dedup hit for host=%s bucket=%s — skipping",
            host_natural_key,
            hour_bucket,
        )
        return None

    rationale = (
        f"Endpoint signal {detection.rule_id} on host {host_natural_key} "
        f"without corroborating identity activity in the last 30 minutes."
    )

    summary = (
        f"Unusual program activity was seen on {host_natural_key}, but no related "
        f"sign-in trouble in the last 30 minutes. Worth a look — could be a "
        f"misbehaving program or an early sign of intrusion."
    )

    incident = Incident(
        id=uuid.uuid4(),
        title=f"Suspicious endpoint activity on {host_natural_key}",
        kind=IncidentKind.endpoint_compromise,
        status=IncidentStatus.new,
        severity=Severity.medium,
        confidence=Decimal("0.60"),
        rationale=rationale,
        summary=summary,
        correlator_version="1.0.0",
        correlator_rule="endpoint_compromise_standalone",
        dedupe_key=dedup_redis_key,
    )
    db.add(incident)
    await db.flush()

    # Trigger event
    db.add(IncidentEvent(
        incident_id=incident.id,
        event_id=event.id,
        role=IncidentEventRole.trigger,
    ))

    # Trigger detection
    db.add(IncidentDetection(incident_id=incident.id, detection_id=detection.id))

    # Host entity
    if host_entity is not None:
        db.add(IncidentEntity(
            incident_id=incident.id,
            entity_id=host_entity.id,
            role=IncidentEntityRole.host,
        ))

    # ATT&CK rows from detection tags
    for tag in detection.attack_tags:
        if "." in tag:
            base = tag.split(".")[0]
            db.add(IncidentAttack(
                incident_id=incident.id,
                tactic="execution",
                technique=base,
                subtechnique=tag,
                source=AttackSource.rule_derived,
            ))
        else:
            db.add(IncidentAttack(
                incident_id=incident.id,
                tactic="execution",
                technique=tag,
                subtechnique=None,
                source=AttackSource.rule_derived,
            ))

    # Initial transition: null → new
    db.add(IncidentTransition(
        incident_id=incident.id,
        from_status=None,
        to_status=IncidentStatus.new,
        actor="system:correlator",
    ))

    log.info(
        "endpoint_compromise_standalone: created incident %s for host=%s rule=%s",
        incident.id,
        host_natural_key,
        detection.rule_id,
    )

    # Do NOT commit here — the events router commits after run_correlators returns
    # and then calls propose_and_execute_auto_actions for auto-tagging.
    return incident.id
