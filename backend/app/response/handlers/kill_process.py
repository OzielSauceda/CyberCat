from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Action, Entity, EvidenceRequest, LabAsset
from app.enums import ActionResult, EntityKind, EvidenceKind, EvidenceStatus, LabAssetKind
from app.response.dispatchers.agent_lookup import agent_id_for_host
from app.response.dispatchers.wazuh_ar import dispatch_ar


async def execute(action: Action, db: AsyncSession) -> tuple[ActionResult, str | None, dict | None]:
    host = action.params.get("host", "")
    pid = action.params.get("pid")
    process_name = action.params.get("process_name", "")

    if not host:
        return ActionResult.fail, "params.host is required", None
    if pid is None:
        return ActionResult.fail, "params.pid is required", None

    asset = await db.scalar(
        select(LabAsset).where(
            LabAsset.kind == LabAssetKind.host,
            LabAsset.natural_key == host,
        )
    )
    if asset is None:
        return ActionResult.fail, f"host {host!r} not found in lab_assets", None

    killed_at = datetime.now(UTC).isoformat()

    # Annotate process entity if present in the entity graph
    process_entity = await db.scalar(
        select(Entity).where(
            Entity.kind == EntityKind.process,
            Entity.natural_key == f"{host}/{pid}",
        )
    )
    if process_entity is not None:
        attrs = dict(process_entity.attrs)
        attrs["killed_at"] = killed_at
        attrs["killed_by_action_id"] = str(action.id)
        process_entity.attrs = attrs

    # Auto-create process_list evidence request for analyst verification
    host_entity = await db.scalar(
        select(Entity).where(
            Entity.kind == EntityKind.host,
            Entity.natural_key == host.lower(),
        )
    )
    evidence = EvidenceRequest(
        id=uuid.uuid4(),
        incident_id=action.incident_id,
        target_host_entity_id=host_entity.id if host_entity else None,
        kind=EvidenceKind.process_list,
        status=EvidenceStatus.open,
    )
    db.add(evidence)

    reversal_info: dict = {
        "host": host,
        "pid": pid,
        "process_name": process_name,
        "killed_at": killed_at,
        "ar_dispatch_status": "disabled",
        "wazuh_command_id": None,
        "ar_response": None,
        "ar_dispatched_at": killed_at,
        "error": None,
    }

    if settings.wazuh_ar_enabled:
        agent_id = await agent_id_for_host(host)
        if agent_id is None:
            reversal_info["ar_dispatch_status"] = "skipped"
            reversal_info["error"] = "wazuh agent not enrolled"
            return ActionResult.partial, "Wazuh agent not enrolled; DB state written", reversal_info

        result = await dispatch_ar(
            command="kill-process0",
            agent_id=agent_id,
            arguments=[host, str(pid), process_name],
        )

        reversal_info["ar_dispatch_status"] = result.status
        reversal_info["wazuh_command_id"] = result.wazuh_command_id
        reversal_info["ar_response"] = result.response
        reversal_info["error"] = result.error

        if result.status == "dispatched":
            return ActionResult.ok, None, reversal_info
        return ActionResult.partial, f"AR dispatch {result.status}: {result.error}", reversal_info

    return ActionResult.ok, None, reversal_info
