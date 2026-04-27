from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.correlation.engine import register
from app.correlation.extend import extend_incident
from app.db.models import Detection, Entity, Event, Incident, IncidentEntity, EventEntity
from app.enums import (
    EntityKind,
    IncidentEntityRole,
    IncidentKind,
    IncidentStatus,
)

log = logging.getLogger(__name__)

_TRIGGER_RULE = "py.process.suspicious_child"
_LOOKBACK_MINUTES = 30
_CLOSED_STATUSES = {IncidentStatus.resolved, IncidentStatus.closed}

# ATT&CK tags surfaced by the endpoint-compromise extension
_ATTACK_TAGS: list[tuple[str, str, str | None]] = [
    ("execution", "T1059", None),
    ("execution", "T1059", "T1059.001"),
]


@register
async def endpoint_compromise_join(
    detection: Detection,
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> uuid.UUID | None:
    if detection.rule_id != _TRIGGER_RULE:
        return None

    # Resolve user and host from the event's entity links (set by entity_extractor)
    ee_result = await db.execute(
        select(Entity, EventEntity.role)
        .join(EventEntity, EventEntity.entity_id == Entity.id)
        .where(EventEntity.event_id == event.id)
    )
    user_entity: Entity | None = None
    host_entity: Entity | None = None
    for entity, role in ee_result.all():
        if entity.kind == EntityKind.user:
            user_entity = entity
        elif entity.kind == EntityKind.host:
            host_entity = entity

    if user_entity is None or host_entity is None:
        log.info(
            "endpoint_compromise_join: event %s missing user or host entity — skipping",
            event.id,
        )
        return None

    # Find open identity_compromise incidents for this user within the lookback window.
    # We key only on user because the identity incident tracks user+source_ip, not yet the
    # endpoint host. The host entity gets added to the incident via extend_incident below.
    window_start = datetime.now(timezone.utc) - timedelta(minutes=_LOOKBACK_MINUTES)

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
    candidates = list(inc_result.scalars().all())

    if not candidates:
        log.info(
            "endpoint_compromise_join: no open identity_compromise incident for "
            "user=%s within %d min — skipping",
            user_entity.natural_key,
            _LOOKBACK_MINUTES,
        )
        return None

    if len(candidates) > 1:
        log.warning(
            "endpoint_compromise_join: %d matching incidents for user=%s host=%s — "
            "extending most recent (%s); others: %s",
            len(candidates),
            user_entity.natural_key,
            host_entity.natural_key,
            candidates[0].id,
            [str(c.id) for c in candidates[1:]],
        )

    incident = candidates[0]

    # Use the attack_tags from the detection to drive ATT&CK rows
    attack_tags = _attack_tags_from_detection(detection)

    await extend_incident(
        db,
        incident,
        event=event,
        detection=detection,
        new_attack_tags=attack_tags,
        entities_by_role={
            IncidentEntityRole.user: user_entity,
            IncidentEntityRole.host: host_entity,
        },
    )

    log.info(
        "endpoint_compromise_join: extended incident %s with process event %s",
        incident.id,
        event.id,
    )

    # Propose and auto-execute an auto_safe tag to make the extension visible in the UI
    await _tag_endpoint_activity(incident.id, db)

    return incident.id


def _attack_tags_from_detection(
    detection: Detection,
) -> list[tuple[str, str, str | None]]:
    """Convert detection.attack_tags strings to (tactic, technique, subtechnique) tuples."""
    result: list[tuple[str, str, str | None]] = []
    for tag in detection.attack_tags:
        if "." in tag:
            base = tag.split(".")[0]
            result.append(("execution", base, tag))
        else:
            result.append(("execution", tag, None))
    # Always include the plain T1059 parent if any sub was added
    has_sub = any(sub is not None for _, _, sub in result)
    if has_sub and not any(t == "T1059" and sub is None for _, t, sub in result):
        result.append(("execution", "T1059", None))
    return result


async def _tag_endpoint_activity(
    incident_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    from app.enums import ActionKind, ActionProposedBy
    from app.response.executor import execute_action, propose_action

    try:
        action = await propose_action(
            db,
            incident_id,
            ActionKind.tag_incident,
            {"tag": "endpoint-activity-observed"},
            ActionProposedBy.system,
        )
        await execute_action(db, action.id, "system:correlator")
    except Exception:
        log.exception(
            "endpoint_compromise_join: auto-tag failed for incident %s — skipping",
            incident_id,
        )
