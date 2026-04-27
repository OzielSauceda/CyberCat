from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActionKind, ActionProposedBy, IncidentKind

log = logging.getLogger(__name__)

# Maps incident kind → list of (ActionKind, params) to propose automatically.
_AUTO_ACTIONS: dict[IncidentKind, list[tuple[ActionKind, dict]]] = {
    IncidentKind.identity_compromise: [
        (ActionKind.tag_incident, {"tag": "identity-compromise-chain"}),
        (ActionKind.elevate_severity, {"to": "high"}),
        (ActionKind.request_evidence, {"evidence_kind": "triage_log"}),
    ],
    IncidentKind.endpoint_compromise: [
        (ActionKind.tag_incident, {"tag": "endpoint-compromise-suspected"}),
    ],
    IncidentKind.identity_endpoint_chain: [
        (ActionKind.tag_incident, {"tag": "cross-layer-chain"}),
        (ActionKind.elevate_severity, {"to": "critical"}),
        (ActionKind.request_evidence, {"evidence_kind": "process_list"}),
        (ActionKind.request_evidence, {"evidence_kind": "triage_log"}),
    ],
}


async def propose_and_execute_auto_actions(
    incident_id: uuid.UUID,
    incident_kind: IncidentKind,
    db: AsyncSession,
) -> None:
    """Propose auto_safe actions for a new incident and execute them immediately.

    Called after the main incident transaction commits. Runs in its own commit so
    that a handler failure cannot roll back the already-committed incident.
    """
    from app.response.executor import execute_action, propose_action

    proposals = _AUTO_ACTIONS.get(incident_kind, [])
    if not proposals:
        return

    for kind, params in proposals:
        try:
            action = await propose_action(db, incident_id, kind, params, ActionProposedBy.system)
            await execute_action(db, action.id, "system:correlator")
        except Exception:
            log.exception(
                "Auto-action %s failed for incident %s — skipping",
                kind.value,
                incident_id,
            )

    try:
        await db.commit()
    except Exception:
        log.exception("Failed to commit auto-actions for incident %s", incident_id)
        await db.rollback()
