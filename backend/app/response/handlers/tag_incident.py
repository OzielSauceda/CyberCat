from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, ActionLog, Incident
from app.enums import ActionResult


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    tag = action.params.get("tag", "")
    if not tag:
        return ActionResult.fail, "params.tag is required", None
    inc = await db.get(Incident, action.incident_id)
    if inc is None:
        return ActionResult.fail, "incident not found", None
    current = list(inc.tags or [])
    if tag not in current:
        current.append(tag)
        inc.tags = current
        inc.updated_at = datetime.now(timezone.utc)
    return ActionResult.ok, None, {"removed_tag": tag}


async def revert(action: Action, log: ActionLog, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    removed_tag = (log.reversal_info or {}).get("removed_tag", "")
    if not removed_tag:
        return ActionResult.fail, "no tag recorded for reversal", None
    inc = await db.get(Incident, action.incident_id)
    if inc is None:
        return ActionResult.fail, "incident not found", None
    inc.tags = [t for t in (inc.tags or []) if t != removed_tag]
    inc.updated_at = datetime.now(timezone.utc)
    return ActionResult.ok, None, None
