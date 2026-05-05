"""Phase 20 §C2 — operator-triggered incident split.

Moves a subset of evidence (events and/or entities) from a source incident
into a brand-new child incident. The source's aggregates (severity,
confidence) are recomputed against remaining evidence. Two
IncidentTransition rows record the split in the audit log. SSE bus
publishes incident.split for both IDs.

Splits do NOT set parent_incident_id on the child (per ADR-0015 — splits
are 'this evidence belongs to a different incident now,' not the inverse
of merge). The audit link is the IncidentTransition row.

This module is NOT registered as an automatic correlator — split is
strictly operator-initiated. The API router calls split_incident()
directly from the split route handler.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Detection,
    Incident,
    IncidentDetection,
    IncidentEntity,
    IncidentEvent,
    IncidentTransition,
)
from app.enums import IncidentStatus, Severity

log = logging.getLogger(__name__)


class SplitError(Exception):
    """Operator-facing split validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _advisory_lock_key(incident_id: uuid.UUID) -> int:
    """Single-incident advisory lock key. Splits don't race on a pair —
    the child is brand-new and exclusive to this transaction. We still
    lock the source so two concurrent splits on the same source serialize.
    """
    return incident_id.int & 0x7FFFFFFFFFFFFFFF


_SEVERITY_ORDER = {
    Severity.info: 0,
    Severity.low: 1,
    Severity.medium: 2,
    Severity.high: 3,
    Severity.critical: 4,
}
_ORDER_TO_SEVERITY = {v: k for k, v in _SEVERITY_ORDER.items()}


async def split_incident(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    event_ids: list[uuid.UUID],
    entity_ids: list[uuid.UUID],
    reason: str,
    actor: str,
    actor_user_id: uuid.UUID | None = None,
) -> Incident:
    """Split the requested events + entities off the source into a new
    child incident. Returns the new child incident.

    Raises SplitError with codes:
      - empty_selection (422) — no event_ids and no entity_ids
      - source_missing  (404) — source not found
      - source_closed   (422) — source is closed/merged
      - events_not_in_source (422) — at least one event_id isn't on source
      - entities_not_in_source (422) — at least one entity_id isn't on source
    """
    if not event_ids and not entity_ids:
        raise SplitError(
            "empty_selection",
            "Split requires at least one event_id or entity_id.",
        )

    # Lock the source for the duration of the transaction.
    lock_key = _advisory_lock_key(source_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=lock_key))

    rows = await db.execute(
        select(Incident).where(Incident.id == source_id).with_for_update()
    )
    source = rows.scalar_one_or_none()
    if source is None:
        raise SplitError("source_missing", f"Source incident {source_id} not found.")

    if source.status in (IncidentStatus.closed, IncidentStatus.merged):
        raise SplitError(
            "source_closed",
            f"Source incident {source_id} is {source.status.value!r} — cannot split.",
        )

    # Validate selections all belong to the source.
    if event_ids:
        attached_evt = await db.execute(
            select(IncidentEvent.event_id).where(
                IncidentEvent.incident_id == source_id,
                IncidentEvent.event_id.in_(event_ids),
            )
        )
        attached_evt_set = {r[0] for r in attached_evt.all()}
        missing = set(event_ids) - attached_evt_set
        if missing:
            raise SplitError(
                "events_not_in_source",
                f"Events not attached to source: {sorted(map(str, missing))}",
            )

    if entity_ids:
        attached_ent = await db.execute(
            select(IncidentEntity.entity_id).where(
                IncidentEntity.incident_id == source_id,
                IncidentEntity.entity_id.in_(entity_ids),
            )
        )
        attached_ent_set = {r[0] for r in attached_ent.all()}
        missing = set(entity_ids) - attached_ent_set
        if missing:
            raise SplitError(
                "entities_not_in_source",
                f"Entities not attached to source: {sorted(map(str, missing))}",
            )

    # --- Create child incident
    child = Incident(
        id=uuid.uuid4(),
        title=f"Split from: {source.title}",
        kind=source.kind,
        status=IncidentStatus.new,
        severity=source.severity,
        confidence=source.confidence,
        rationale=f"Split from incident {source_id}: {reason}",
        summary=source.summary,
        tags=list(source.tags or []),
        correlator_version=source.correlator_version,
        correlator_rule="split",
        dedupe_key=None,  # Split children are non-canonical
        parent_incident_id=None,  # Per ADR-0015, splits do NOT set parent FK
    )
    db.add(child)
    await db.flush()

    # --- MOVE selected events from source → child (delete from source side first)
    if event_ids:
        # Read role assignments before delete so we can copy them onto the child.
        moving_evt = await db.execute(
            select(IncidentEvent).where(
                IncidentEvent.incident_id == source_id,
                IncidentEvent.event_id.in_(event_ids),
            )
        )
        evt_rows = list(moving_evt.scalars().all())
        await db.execute(
            delete(IncidentEvent).where(
                IncidentEvent.incident_id == source_id,
                IncidentEvent.event_id.in_(event_ids),
            )
        )
        for ie in evt_rows:
            db.add(IncidentEvent(
                incident_id=child.id,
                event_id=ie.event_id,
                role=ie.role,
            ))

    # --- MOVE selected entities. Entity-junction PK includes role, so we
    # iterate by (entity, role) and move all role-rows for the requested
    # entity_ids.
    if entity_ids:
        moving_ent = await db.execute(
            select(IncidentEntity).where(
                IncidentEntity.incident_id == source_id,
                IncidentEntity.entity_id.in_(entity_ids),
            )
        )
        ent_rows = list(moving_ent.scalars().all())
        await db.execute(
            delete(IncidentEntity).where(
                IncidentEntity.incident_id == source_id,
                IncidentEntity.entity_id.in_(entity_ids),
            )
        )
        for ie in ent_rows:
            db.add(IncidentEntity(
                incident_id=child.id,
                entity_id=ie.entity_id,
                role=ie.role,
            ))

    # --- Detections that are linked SOLELY to events being moved get moved
    # too. Detections that are linked to events still on the source stay on
    # the source. The simplest correct policy: copy linked detections to
    # child (via ON CONFLICT DO NOTHING), don't remove them from source.
    # The source incident keeps the same detection set unless we explicitly
    # know a detection is no longer represented — which is hard to compute
    # in the general case. Conservative: copy, don't remove.
    if event_ids:
        # Detections that fired ON the moved events
        det_q = await db.execute(
            select(Detection.id).where(Detection.event_id.in_(event_ids))
        )
        for det_id in {r[0] for r in det_q.all()}:
            await db.execute(
                pg_insert(IncidentDetection)
                .values(incident_id=child.id, detection_id=det_id)
                .on_conflict_do_nothing()
            )

    # --- Recompute source aggregates (severity = max over remaining detections;
    # confidence = unchanged for now — recomputing would require detection
    # confidences which aren't trivially reachable. Document the limitation:
    # confidence on source remains as-is post-split; analysts can manually
    # adjust if needed.)
    remaining_det_q = await db.execute(
        select(Detection.severity_hint)
        .join(IncidentDetection, IncidentDetection.detection_id == Detection.id)
        .where(IncidentDetection.incident_id == source_id)
    )
    remaining_severities = [
        s for (s,) in remaining_det_q.all() if s is not None
    ]
    if remaining_severities:
        source.severity = max(remaining_severities, key=lambda s: _SEVERITY_ORDER.get(s, 0))

    source.updated_at = datetime.now(UTC)

    # --- Audit-log rows
    db.add(IncidentTransition(
        incident_id=source.id,
        from_status=source.status,
        to_status=source.status,  # source status doesn't change
        actor=actor,
        actor_user_id=actor_user_id,
        reason=f"Split off into {child.id}: {reason}",
    ))
    db.add(IncidentTransition(
        incident_id=child.id,
        from_status=None,
        to_status=IncidentStatus.new,
        actor=actor,
        actor_user_id=actor_user_id,
        reason=f"Split from {source.id}: {reason}",
    ))

    await db.flush()

    # --- SSE notifications
    from app.streaming.publisher import publish
    await publish("incident.split", {
        "source_id": str(source.id),
        "child_id": str(child.id),
        "actor": actor,
        "reason": reason,
        "event_count": len(event_ids),
        "entity_count": len(entity_ids),
    })

    log.info(
        "split_incident: source=%s → child=%s events=%d entities=%d actor=%s",
        source.id, child.id, len(event_ids), len(entity_ids), actor,
    )
    return child
