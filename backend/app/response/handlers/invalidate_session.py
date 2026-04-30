from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, ActionLog, Entity, LabAsset, LabSession
from app.enums import ActionResult, EntityKind, LabAssetKind


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    user = action.params.get("user", "")
    host = action.params.get("host", "")
    if not user:
        return ActionResult.fail, "params.user is required", None
    if not host:
        return ActionResult.fail, "params.host is required", None

    user_asset = await db.scalar(
        select(LabAsset).where(
            LabAsset.kind == LabAssetKind.user,
            LabAsset.natural_key == user,
        )
    )
    if user_asset is None:
        return ActionResult.fail, f"user {user!r} not found in lab_assets", None

    host_asset = await db.scalar(
        select(LabAsset).where(
            LabAsset.kind == LabAssetKind.host,
            LabAsset.natural_key == host,
        )
    )
    if host_asset is None:
        return ActionResult.fail, f"host {host!r} not found in lab_assets", None

    user_entity = await db.scalar(
        select(Entity).where(
            Entity.kind == EntityKind.user,
            Entity.natural_key == user.lower(),
        )
    )
    host_entity = await db.scalar(
        select(Entity).where(
            Entity.kind == EntityKind.host,
            Entity.natural_key == host.lower(),
        )
    )
    if user_entity is None or host_entity is None:
        return ActionResult.fail, "no session entities found; ingest an auth or session event first", None

    # Find active (non-invalidated) session; create one if absent
    session = await db.scalar(
        select(LabSession)
        .where(
            LabSession.user_entity_id == user_entity.id,
            LabSession.host_entity_id == host_entity.id,
            LabSession.invalidated_at.is_(None),
        )
        .order_by(LabSession.opened_at.desc())
        .limit(1)
    )
    if session is None:
        session = LabSession(
            user_entity_id=user_entity.id,
            host_entity_id=host_entity.id,
        )
        db.add(session)
        await db.flush()

    prior_invalidated_at = (
        session.invalidated_at.isoformat() if session.invalidated_at else None
    )
    session.invalidated_at = datetime.now(UTC)
    session.invalidated_by_action_id = action.id

    return ActionResult.ok, None, {
        "session_id": str(session.id),
        "prior_invalidated_at": prior_invalidated_at,
    }


async def revert(
    action: Action, log: ActionLog, db: AsyncSession
) -> tuple[ActionResult, str | None, dict | None]:
    session_id = (log.reversal_info or {}).get("session_id")
    if not session_id:
        return ActionResult.fail, "no session_id in reversal_info", None

    session = await db.get(LabSession, uuid.UUID(session_id))
    if session is None:
        return ActionResult.fail, f"lab_session {session_id!r} not found", None

    session.invalidated_at = None
    session.invalidated_by_action_id = None
    await db.flush()
    return ActionResult.ok, None, None
