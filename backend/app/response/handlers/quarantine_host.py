from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Action, LabAsset, Note
from app.enums import ActionResult, LabAssetKind
from app.response.dispatchers.agent_lookup import agent_id_for_host
from app.response.dispatchers.wazuh_ar import dispatch_ar

_MARKER_PREFIX = "[quarantined:"


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

    ts = datetime.now(UTC).isoformat()
    marker = f"[quarantined:incident-{action.incident_id}:at-{ts}]"
    prior_notes = asset.notes or ""
    if _MARKER_PREFIX not in prior_notes:
        asset.notes = f"{marker} {prior_notes}".strip()

    note = Note(
        incident_id=action.incident_id,
        body=f"Host {host} quarantined by action #{action.id}",
        author="system:response",
    )
    db.add(note)

    ar_info: dict = {
        "ar_dispatch_status": "disabled",
        "wazuh_command_id": None,
        "ar_response": None,
        "ar_dispatched_at": ts,
        "error": None,
    }

    if settings.wazuh_ar_enabled:
        agent_id = await agent_id_for_host(host)
        if agent_id is None:
            ar_info["ar_dispatch_status"] = "skipped"
            ar_info["error"] = "wazuh agent not enrolled"
            note.body += " | AR: skipped (agent not enrolled)"
            return ActionResult.partial, "Wazuh agent not enrolled; DB state written", ar_info

        # Extract source_ip from incident entities (best-effort)
        source_ip = action.params.get("source_ip", "0.0.0.0")

        result = await dispatch_ar(
            command="firewall-drop0",
            agent_id=agent_id,
            arguments=[],
            alert={"data": {"srcip": source_ip}},
        )

        ar_info["ar_dispatch_status"] = result.status
        ar_info["wazuh_command_id"] = result.wazuh_command_id
        ar_info["ar_response"] = result.response
        ar_info["error"] = result.error

        note.body += f" | AR: {result.status}"
        if result.error:
            note.body += f" ({result.error})"

        if result.status == "dispatched":
            return ActionResult.ok, None, ar_info
        return ActionResult.partial, f"AR dispatch {result.status}: {result.error}", ar_info

    return ActionResult.ok, None, ar_info
