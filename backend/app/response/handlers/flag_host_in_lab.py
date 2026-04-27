from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, ActionLog, LabAsset
from app.enums import ActionResult, LabAssetKind

_MARKER = "[under-investigation]"


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    host = action.params.get("host", "")
    if not host:
        return ActionResult.fail, "params.host is required", None
    asset = await db.scalar(
        select(LabAsset).where(
            LabAsset.kind == LabAssetKind.host,
            LabAsset.natural_key == host,
        )
    )
    if asset is None:
        return ActionResult.fail, f"host {host!r} not found in lab_assets", None
    prior_notes = asset.notes or ""
    if _MARKER not in prior_notes:
        asset.notes = f"{_MARKER} {prior_notes}".strip()
    return ActionResult.ok, None, {"prior_notes": prior_notes}


async def revert(action: Action, log: ActionLog, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    host = action.params.get("host", "")
    prior_notes = (log.reversal_info or {}).get("prior_notes")
    if prior_notes is None:
        return ActionResult.fail, "no prior notes recorded for reversal", None
    asset = await db.scalar(
        select(LabAsset).where(
            LabAsset.kind == LabAssetKind.host,
            LabAsset.natural_key == host,
        )
    )
    if asset is None:
        return ActionResult.fail, f"host {host!r} not found in lab_assets", None
    asset.notes = prior_notes
    return ActionResult.ok, None, None
