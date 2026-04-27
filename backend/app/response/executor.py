from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Action, ActionLog, LabAsset
from app.enums import (
    ActionClassification,
    ActionKind,
    ActionProposedBy,
    ActionResult,
    ActionStatus,
    LabAssetKind,
)
from app.response import policy
from app.response.handlers import (
    block_observable,
    elevate_severity,
    flag_host_in_lab,
    invalidate_session,
    kill_process,
    quarantine_host,
    request_evidence,
    tag_incident,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class OutOfLabScopeError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ActionStateError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Handler type alias and registry
# ---------------------------------------------------------------------------

_ExecuteFn = Callable[[Action, AsyncSession], Awaitable[tuple[ActionResult, str | None, dict | None]]]
_RevertFn = Callable[[Action, ActionLog, AsyncSession], Awaitable[tuple[ActionResult, str | None, dict | None]]]

_EXECUTE: dict[ActionKind, _ExecuteFn] = {
    ActionKind.tag_incident: tag_incident.execute,
    ActionKind.elevate_severity: elevate_severity.execute,
    ActionKind.flag_host_in_lab: flag_host_in_lab.execute,
    ActionKind.quarantine_host_lab: quarantine_host.execute,
    ActionKind.invalidate_lab_session: invalidate_session.execute,
    ActionKind.block_observable: block_observable.execute,
    ActionKind.kill_process_lab: kill_process.execute,
    ActionKind.request_evidence: request_evidence.execute,
}

# Only reversible action kinds are registered; executor guards via classification check.
_REVERT: dict[ActionKind, _RevertFn] = {
    ActionKind.tag_incident: tag_incident.revert,
    ActionKind.elevate_severity: elevate_severity.revert,
    ActionKind.flag_host_in_lab: flag_host_in_lab.revert,
    ActionKind.invalidate_lab_session: invalidate_session.revert,
    ActionKind.block_observable: block_observable.revert,
}

# ---------------------------------------------------------------------------
# Lab scope check
# ---------------------------------------------------------------------------

_SCOPE_CHECKS: dict[ActionKind, list[tuple[LabAssetKind, str]]] = {
    ActionKind.flag_host_in_lab: [(LabAssetKind.host, "host")],
    ActionKind.quarantine_host_lab: [(LabAssetKind.host, "host")],
    ActionKind.invalidate_lab_session: [(LabAssetKind.user, "user")],
    ActionKind.kill_process_lab: [(LabAssetKind.host, "host")],
    # block_observable is platform-global — no lab-scope restriction
}


async def _check_lab_scope(kind: ActionKind, params: dict, db: AsyncSession) -> None:
    for asset_kind, param_key in _SCOPE_CHECKS.get(kind, []):
        natural_key = params.get(param_key)
        if not natural_key:
            continue
        exists = await db.scalar(
            select(LabAsset.id).where(
                LabAsset.kind == asset_kind,
                LabAsset.natural_key == natural_key,
            )
        )
        if not exists:
            raise OutOfLabScopeError(f"{asset_kind.value}:{natural_key} is not registered in lab_assets")


# ---------------------------------------------------------------------------
# Public API — callers commit their own session
# ---------------------------------------------------------------------------

async def propose_action(
    db: AsyncSession,
    incident_id: uuid.UUID,
    kind: ActionKind,
    params: dict,
    proposed_by: ActionProposedBy,
) -> Action:
    await _check_lab_scope(kind, params, db)
    decision = policy.classify(kind)
    action = Action(
        id=uuid.uuid4(),
        incident_id=incident_id,
        kind=kind,
        classification=decision.classification,
        classification_reason=decision.reason,
        params=params,
        proposed_by=proposed_by,
        status=ActionStatus.proposed,
    )
    db.add(action)
    await db.flush()
    return action


async def execute_action(
    db: AsyncSession,
    action_id: uuid.UUID,
    executed_by: str,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[Action, ActionLog]:
    action = await db.get(Action, action_id)
    if action is None:
        raise ActionStateError("action_not_found", "Action not found")
    if action.status != ActionStatus.proposed:
        raise ActionStateError(
            "action_not_proposed",
            f"Action is {action.status.value}, not proposed",
        )

    await _check_lab_scope(action.kind, action.params, db)

    handler = _EXECUTE[action.kind]
    result, reason, reversal_info = await handler(action, db)

    new_status = {
        ActionResult.ok: ActionStatus.executed,
        ActionResult.fail: ActionStatus.failed,
        ActionResult.skipped: ActionStatus.skipped,
        ActionResult.partial: ActionStatus.partial,
    }[result]

    action.status = new_status
    log = ActionLog(
        action_id=action.id,
        executed_at=datetime.now(timezone.utc),
        executed_by=executed_by,
        result=result,
        reason=reason,
        reversal_info=reversal_info,
        actor_user_id=actor_user_id,
    )
    db.add(log)
    await db.flush()
    return action, log


async def revert_action(
    db: AsyncSession,
    action_id: uuid.UUID,
    executed_by: str,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[Action, ActionLog]:
    action = await db.get(Action, action_id)
    if action is None:
        raise ActionStateError("action_not_found", "Action not found")
    if action.status != ActionStatus.executed:
        raise ActionStateError("not_reversible", "Action is not in executed state")
    if action.classification not in (ActionClassification.reversible,):
        raise ActionStateError("not_reversible", "Action classification is not reversible")

    # Load the most recent executed log row to get reversal_info
    log_result = await db.execute(
        select(ActionLog)
        .where(ActionLog.action_id == action_id, ActionLog.result == ActionResult.ok)
        .order_by(desc(ActionLog.executed_at))
        .limit(1)
    )
    prior_log = log_result.scalar_one_or_none()
    if prior_log is None or not prior_log.reversal_info:
        raise ActionStateError("not_reversible", "No reversal_info recorded on the execution log")

    handler = _REVERT.get(action.kind)
    if handler is None:
        raise ActionStateError("not_reversible", f"No revert handler registered for {action.kind.value}")
    result, reason, _ = await handler(action, prior_log, db)

    action.status = ActionStatus.reverted
    revert_log = ActionLog(
        action_id=action.id,
        executed_at=datetime.now(timezone.utc),
        executed_by=executed_by,
        result=result,
        reason=reason,
        reversal_info=None,
        actor_user_id=actor_user_id,
    )
    db.add(revert_log)
    await db.flush()
    return action, revert_log
