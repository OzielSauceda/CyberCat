from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Detection,
    Entity,
    Event,
    Incident,
    IncidentAttack,
    IncidentDetection,
    IncidentEntity,
    IncidentEvent,
)
from app.enums import AttackSource, IncidentEntityRole, IncidentEventRole


async def extend_incident(
    db: AsyncSession,
    incident: Incident,
    *,
    event: Event,
    detection: Detection | None,
    new_attack_tags: list[tuple[str, str, str | None]],
    entities_by_role: dict[IncidentEntityRole, Entity],
) -> None:
    """Add new evidence to an existing incident idempotently.

    All junction inserts use ON CONFLICT DO NOTHING so re-entry is safe.
    IncidentAttack uses a select-before-insert because its unique constraint
    is an expression index (COALESCE) which pg_insert cannot reference directly.
    """
    # Link event as context role
    await db.execute(
        pg_insert(IncidentEvent)
        .values(
            incident_id=incident.id,
            event_id=event.id,
            role=IncidentEventRole.context,
        )
        .on_conflict_do_nothing()
    )

    # Link detection
    if detection is not None:
        await db.execute(
            pg_insert(IncidentDetection)
            .values(incident_id=incident.id, detection_id=detection.id)
            .on_conflict_do_nothing()
        )

    # Link entities
    for role, entity in entities_by_role.items():
        await db.execute(
            pg_insert(IncidentEntity)
            .values(
                incident_id=incident.id,
                entity_id=entity.id,
                role=role,
            )
            .on_conflict_do_nothing()
        )

    # Link ATT&CK — select-before-insert due to expression unique index
    for tactic, technique, subtechnique in new_attack_tags:
        atk_q = select(IncidentAttack.id).where(
            IncidentAttack.incident_id == incident.id,
            IncidentAttack.tactic == tactic,
            IncidentAttack.technique == technique,
        )
        if subtechnique:
            atk_q = atk_q.where(IncidentAttack.subtechnique == subtechnique)
        else:
            atk_q = atk_q.where(IncidentAttack.subtechnique.is_(None))

        existing = await db.execute(atk_q)
        if existing.scalar_one_or_none() is None:
            db.add(IncidentAttack(
                incident_id=incident.id,
                tactic=tactic,
                technique=technique,
                subtechnique=subtechnique,
                source=AttackSource.correlator_inferred,
            ))

    # Bump updated_at
    incident.updated_at = datetime.now(timezone.utc)
    await db.flush()
