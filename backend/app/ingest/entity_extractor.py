from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entity, Event, EventEntity, LabAsset, LabSession
from app.enums import EntityKind, EventEntityRole, LabAssetKind


@dataclass
class _EntitySpec:
    kind: EntityKind
    natural_key: str
    role: EventEntityRole


def _specs_for_event(event: Event) -> list[_EntitySpec]:
    n = event.normalized
    kind = event.kind

    if kind in ("auth.failed", "auth.succeeded"):
        specs = []
        if user := n.get("user"):
            specs.append(_EntitySpec(EntityKind.user, user.lower(), EventEntityRole.actor))
        if ip := n.get("source_ip"):
            specs.append(_EntitySpec(EntityKind.ip, ip, EventEntityRole.source_ip))
        return specs

    if kind in ("session.started", "session.ended"):
        specs = []
        if user := n.get("user"):
            specs.append(_EntitySpec(EntityKind.user, user.lower(), EventEntityRole.actor))
        if host := n.get("host"):
            specs.append(_EntitySpec(EntityKind.host, host.lower(), EventEntityRole.host))
        return specs

    if kind == "process.created":
        specs = []
        if host := n.get("host"):
            specs.append(_EntitySpec(EntityKind.host, host.lower(), EventEntityRole.host))
        if user := n.get("user"):
            specs.append(_EntitySpec(EntityKind.user, user.lower(), EventEntityRole.actor))
        return specs

    if kind == "process.exited":
        specs = []
        if host := n.get("host"):
            specs.append(_EntitySpec(EntityKind.host, host.lower(), EventEntityRole.host))
        return specs

    if kind == "file.created":
        specs = []
        if host := n.get("host"):
            specs.append(_EntitySpec(EntityKind.host, host.lower(), EventEntityRole.host))
        if user := n.get("user"):
            specs.append(_EntitySpec(EntityKind.user, user.lower(), EventEntityRole.actor))
        return specs

    if kind == "network.connection":
        specs = []
        if host := n.get("host"):
            specs.append(_EntitySpec(EntityKind.host, host.lower(), EventEntityRole.host))
        if src := n.get("src_ip"):
            specs.append(_EntitySpec(EntityKind.ip, src, EventEntityRole.source_ip))
        return specs

    return []


async def extract_and_link_entities(event: Event, db: AsyncSession) -> None:
    occurred_at: datetime = event.occurred_at
    specs = _specs_for_event(event)
    extracted: dict[str, uuid.UUID] = {}  # EntityKind.value → last entity_id upserted

    for spec in specs:
        # Upsert entity: insert or update last_seen
        entity_stmt = (
            pg_insert(Entity)
            .values(
                id=uuid.uuid4(),
                kind=spec.kind,
                natural_key=spec.natural_key,
                attrs={},
                first_seen=occurred_at,
                last_seen=occurred_at,
            )
            .on_conflict_do_update(
                constraint="uq_entities_kind_natural_key",
                set_={"last_seen": occurred_at},
            )
            .returning(Entity.id)
        )
        result = await db.execute(entity_stmt)
        entity_id: uuid.UUID = result.scalar_one()
        extracted[spec.kind.value] = entity_id

        # Link event → entity (ignore if already linked with same role)
        link_stmt = (
            pg_insert(EventEntity)
            .values(
                event_id=event.id,
                entity_id=entity_id,
                role=spec.role,
            )
            .on_conflict_do_nothing()
        )
        await db.execute(link_stmt)

    if event.kind == "session.started":
        await _maybe_create_lab_session(event, extracted, db)


async def _maybe_create_lab_session(
    event: Event,
    extracted: dict[str, uuid.UUID],
    db: AsyncSession,
) -> None:
    """Create a LabSession row when both the user and host are registered lab assets."""
    user_id = extracted.get("user")
    host_id = extracted.get("host")
    if user_id is None or host_id is None:
        return

    user_key = event.normalized.get("user", "")
    host_key = event.normalized.get("host", "")

    user_is_lab = await db.scalar(
        select(LabAsset.id).where(
            LabAsset.kind == LabAssetKind.user,
            LabAsset.natural_key == user_key,
        )
    )
    if not user_is_lab:
        return

    host_is_lab = await db.scalar(
        select(LabAsset.id).where(
            LabAsset.kind == LabAssetKind.host,
            LabAsset.natural_key == host_key,
        )
    )
    if not host_is_lab:
        return

    session = LabSession(user_entity_id=user_id, host_entity_id=host_id)
    db.add(session)
