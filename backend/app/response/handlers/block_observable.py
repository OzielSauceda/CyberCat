from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, ActionLog, BlockedObservable
from app.enums import ActionResult, BlockableKind

_CACHE_KEY = "cybercat:blocked_observables:active"


async def _invalidate_cache() -> None:
    try:
        from app.db.redis import get_redis
        await get_redis().delete(_CACHE_KEY)
    except Exception:
        pass


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    kind_str = action.params.get("kind", "")
    value = action.params.get("value", "")
    if not kind_str:
        return ActionResult.fail, "params.kind is required", None
    if not value:
        return ActionResult.fail, "params.value is required", None

    try:
        kind = BlockableKind(kind_str)
    except ValueError:
        valid = ", ".join(k.value for k in BlockableKind)
        return ActionResult.fail, f"invalid kind {kind_str!r}; must be one of: {valid}", None

    observable = BlockedObservable(
        id=uuid.uuid4(),
        kind=kind,
        value=value,
        blocked_by_action_id=action.id,
        active=True,
    )
    db.add(observable)
    await db.flush()
    await _invalidate_cache()

    return ActionResult.ok, None, {"blocked_observable_id": str(observable.id)}


async def revert(
    action: Action, log: ActionLog, db: AsyncSession
) -> tuple[ActionResult, str | None, dict | None]:
    observable_id = (log.reversal_info or {}).get("blocked_observable_id")
    if not observable_id:
        return ActionResult.fail, "no blocked_observable_id in reversal_info", None

    observable = await db.get(BlockedObservable, uuid.UUID(observable_id))
    if observable is None:
        return ActionResult.fail, f"blocked_observable {observable_id!r} not found", None

    observable.active = False
    await db.flush()
    await _invalidate_cache()
    return ActionResult.ok, None, None
