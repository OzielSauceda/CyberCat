from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, Entity, EvidenceRequest
from app.enums import ActionResult, EntityKind, EvidenceKind, EvidenceStatus


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    evidence_kind_str = action.params.get("evidence_kind", "")
    target_host = action.params.get("target_host")

    if not evidence_kind_str:
        return ActionResult.fail, "params.evidence_kind is required", None

    try:
        kind = EvidenceKind(evidence_kind_str)
    except ValueError:
        valid = ", ".join(k.value for k in EvidenceKind)
        return ActionResult.fail, f"invalid evidence_kind {evidence_kind_str!r}; must be one of: {valid}", None

    host_entity_id = None
    if target_host:
        host_entity = await db.scalar(
            select(Entity).where(
                Entity.kind == EntityKind.host,
                Entity.natural_key == target_host.lower(),
            )
        )
        if host_entity is not None:
            host_entity_id = host_entity.id

    evidence = EvidenceRequest(
        id=uuid.uuid4(),
        incident_id=action.incident_id,
        target_host_entity_id=host_entity_id,
        kind=kind,
        status=EvidenceStatus.open,
    )
    db.add(evidence)
    await db.flush()

    return ActionResult.ok, None, {"evidence_request_id": str(evidence.id), "kind": kind.value}
