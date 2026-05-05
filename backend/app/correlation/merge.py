"""Phase 20 §C2 — operator-triggered incident merge.

Bulk-moves all evidence (events, entities, detections, ATT&CK tags) from a
source incident into a target incident. Source becomes status=merged with
parent_incident_id pointing at the target. Two IncidentTransition rows
record the merge in the audit log. SSE bus publishes incident.merged for
both IDs.

Concurrency: Postgres advisory lock keyed on the deterministic
(min(src,tgt), max(src,tgt)) pair prevents two operators racing on the
same incident pair.

This module is NOT registered as an automatic correlator — merge is
strictly operator-initiated. The API router calls merge_incidents()
directly from the merge-into route handler.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Incident,
    IncidentAttack,
    IncidentDetection,
    IncidentEntity,
    IncidentEvent,
    IncidentTransition,
)
from app.enums import IncidentStatus
from app.streaming.publisher import publish

log = logging.getLogger(__name__)


class MergeError(Exception):
    """Operator-facing merge validation error. The API maps to 4xx codes
    by inspecting the .code attribute."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _advisory_lock_key(a: uuid.UUID, b: uuid.UUID) -> int:
    """Deterministic 64-bit lock key for an unordered (incident, incident)
    pair. Postgres advisory locks take int8; we hash the canonicalized
    (min, max) pair into a stable int64.

    Why this matters: if two operators click "merge A → B" and "merge B → A"
    simultaneously, both routes compute the same key and serialize on the
    same lock — preventing a race where both transactions try to mutate
    the same rows.
    """
    lo, hi = sorted((a, b))
    # Take the low 63 bits of the XOR of the two UUIDs' int128 values.
    # Postgres advisory locks accept int8 (signed 64-bit), so mask to 63
    # bits to stay safely positive.
    raw = (lo.int ^ hi.int) & 0x7FFFFFFFFFFFFFFF
    return raw


async def merge_incidents(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    reason: str,
    actor: str,
    actor_user_id: uuid.UUID | None = None,
) -> Incident:
    """Merge source into target. Returns the (refreshed) target incident.

    Raises MergeError with codes:
      - self_merge      (422) — source_id == target_id
      - source_missing  (404) — source not found
      - target_missing  (404) — target not found
      - source_merged   (409) — source.status == 'merged' already
      - target_closed   (409) — target.status in {'closed','merged'}
    """
    if source_id == target_id:
        raise MergeError("self_merge", "Cannot merge an incident into itself.")

    # Advisory lock — held until end of transaction. xact_lock = released on
    # COMMIT/ROLLBACK so we don't have to manually unlock.
    lock_key = _advisory_lock_key(source_id, target_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=lock_key))

    # SELECT ... FOR UPDATE on both rows. Order by id to avoid deadlocks
    # if two transactions hold the lock and grab rows in different orders.
    lo, hi = sorted((source_id, target_id))
    rows = await db.execute(
        select(Incident).where(Incident.id.in_([lo, hi])).with_for_update()
    )
    by_id: dict[uuid.UUID, Incident] = {inc.id: inc for inc in rows.scalars().all()}

    source = by_id.get(source_id)
    target = by_id.get(target_id)

    if source is None:
        raise MergeError("source_missing", f"Source incident {source_id} not found.")
    if target is None:
        raise MergeError("target_missing", f"Target incident {target_id} not found.")

    if source.status == IncidentStatus.merged:
        raise MergeError(
            "source_merged",
            f"Source incident {source_id} has already been merged into another.",
        )
    if target.status in (IncidentStatus.closed, IncidentStatus.merged):
        raise MergeError(
            "target_closed",
            f"Target incident {target_id} is {target.status.value!r} — cannot merge into it.",
        )

    # --- Bulk-move junctions. ON CONFLICT DO NOTHING because target may
    # already have some of these rows (e.g., overlapping events).

    # Events: copy with role='context' if not already linked
    src_events = await db.execute(
        select(IncidentEvent).where(IncidentEvent.incident_id == source_id)
    )
    for ie in src_events.scalars().all():
        await db.execute(
            pg_insert(IncidentEvent)
            .values(
                incident_id=target_id,
                event_id=ie.event_id,
                role=ie.role,
            )
            .on_conflict_do_nothing()
        )

    # Entities
    src_entities = await db.execute(
        select(IncidentEntity).where(IncidentEntity.incident_id == source_id)
    )
    for ie in src_entities.scalars().all():
        await db.execute(
            pg_insert(IncidentEntity)
            .values(
                incident_id=target_id,
                entity_id=ie.entity_id,
                role=ie.role,
            )
            .on_conflict_do_nothing()
        )

    # Detections
    src_dets = await db.execute(
        select(IncidentDetection).where(IncidentDetection.incident_id == source_id)
    )
    for id_ in src_dets.scalars().all():
        await db.execute(
            pg_insert(IncidentDetection)
            .values(incident_id=target_id, detection_id=id_.detection_id)
            .on_conflict_do_nothing()
        )

    # ATT&CK — select-before-insert (expression unique index)
    src_attack = await db.execute(
        select(IncidentAttack).where(IncidentAttack.incident_id == source_id)
    )
    for atk in src_attack.scalars().all():
        existing_q = select(IncidentAttack.id).where(
            IncidentAttack.incident_id == target_id,
            IncidentAttack.tactic == atk.tactic,
            IncidentAttack.technique == atk.technique,
        )
        if atk.subtechnique:
            existing_q = existing_q.where(IncidentAttack.subtechnique == atk.subtechnique)
        else:
            existing_q = existing_q.where(IncidentAttack.subtechnique.is_(None))
        existing = await db.execute(existing_q)
        if existing.scalar_one_or_none() is None:
            db.add(IncidentAttack(
                incident_id=target_id,
                tactic=atk.tactic,
                technique=atk.technique,
                subtechnique=atk.subtechnique,
                source=atk.source,
            ))

    # --- Aggregate updates on target
    target.severity = max(source.severity, target.severity, key=_severity_ord)
    # Average confidence, capped at 1.00, with 2-decimal rounding to match
    # Numeric(3, 2).
    avg = (source.confidence + target.confidence) / Decimal(2)
    target.confidence = avg.quantize(Decimal("0.01"))
    target.updated_at = datetime.now(UTC)

    # --- Source: mark merged + parent FK
    prev_status = source.status
    source.status = IncidentStatus.merged
    source.parent_incident_id = target.id
    source.updated_at = datetime.now(UTC)

    # --- Audit-log rows (one for each side)
    db.add(IncidentTransition(
        incident_id=source.id,
        from_status=prev_status,
        to_status=IncidentStatus.merged,
        actor=actor,
        actor_user_id=actor_user_id,
        reason=f"Merged into {target.id}: {reason}",
    ))
    db.add(IncidentTransition(
        incident_id=target.id,
        from_status=target.status,
        to_status=target.status,  # target's status doesn't change
        actor=actor,
        actor_user_id=actor_user_id,
        reason=f"Absorbed merge from {source.id}: {reason}",
    ))

    await db.flush()

    # --- SSE notifications (after flush; before commit — bus is best-effort)
    await publish("incident.merged", {
        "source_id": str(source.id),
        "target_id": str(target.id),
        "actor": actor,
        "reason": reason,
    })

    log.info(
        "merge_incidents: source=%s → target=%s actor=%s",
        source.id, target.id, actor,
    )
    return target


_SEVERITY_ORDINAL = {
    "info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4,
}


def _severity_ord(s) -> int:
    return _SEVERITY_ORDINAL.get(getattr(s, "value", str(s)), 0)
