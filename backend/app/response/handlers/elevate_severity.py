from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, ActionLog, Incident
from app.enums import ActionResult, Severity


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    to_sev_raw = action.params.get("to", "")
    if not to_sev_raw:
        return ActionResult.fail, "params.to is required", None
    try:
        new_sev = Severity(to_sev_raw)
    except ValueError:
        return ActionResult.fail, f"unknown severity value: {to_sev_raw!r}", None
    inc = await db.get(Incident, action.incident_id)
    if inc is None:
        return ActionResult.fail, "incident not found", None
    prior = inc.severity.value
    inc.severity = new_sev
    inc.updated_at = datetime.now(timezone.utc)
    return ActionResult.ok, None, {"prior_severity": prior}


async def revert(action: Action, log: ActionLog, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    prior_raw = (log.reversal_info or {}).get("prior_severity")
    if not prior_raw:
        return ActionResult.fail, "no prior severity recorded for reversal", None
    inc = await db.get(Incident, action.incident_id)
    if inc is None:
        return ActionResult.fail, "incident not found", None
    inc.severity = Severity(prior_raw)
    inc.updated_at = datetime.now(timezone.utc)
    return ActionResult.ok, None, None
