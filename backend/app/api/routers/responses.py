from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.errors import ErrorEnvelope
from app.api.schemas.incidents import ActionLogSummary, ActionSummary
from app.api.schemas.responses import ActionExecuted, ActionProposed, ActionProposeIn, ResponseList
from app.auth.dependencies import SystemUser, require_analyst, require_user, resolve_actor_id
from app.auth.models import User
from app.db.models import Action, ActionLog
from app.db.session import get_db
from app.enums import ActionClassification, ActionKind, ActionProposedBy, ActionStatus
from app.response.executor import (
    ActionStateError,
    OutOfLabScopeError,
    execute_action,
    propose_action,
    revert_action,
)
from app.streaming.publisher import publish

router = APIRouter(prefix="/responses", tags=["responses"])


def _action_to_summary(act: Action, last_log: ActionLog | None) -> ActionSummary:
    log_out = (
        ActionLogSummary(
            executed_at=last_log.executed_at,
            executed_by=last_log.executed_by,
            result=last_log.result.value,
            reason=last_log.reason,
            reversal_info=last_log.reversal_info,
            actor_user_id=last_log.actor_user_id,
        )
        if last_log
        else None
    )
    return ActionSummary(
        id=act.id,
        kind=act.kind.value,
        classification=act.classification.value,
        classification_reason=act.classification_reason,
        status=act.status.value,
        params=act.params,
        proposed_by=act.proposed_by.value,
        proposed_at=act.proposed_at,
        last_log=log_out,
    )


async def _load_last_log(action_id: uuid.UUID, db: AsyncSession) -> ActionLog | None:
    result = await db.execute(
        select(ActionLog)
        .where(ActionLog.action_id == action_id)
        .order_by(desc(ActionLog.executed_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("", response_model=ResponseList)
async def list_responses(
    db: AsyncSession = Depends(get_db),
    _user: User | SystemUser = Depends(require_user),
    incident_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query(description="ISO 8601 datetime; return actions proposed after this time")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResponseList:
    q = select(Action).order_by(Action.proposed_at.desc())
    if incident_id:
        q = q.where(Action.incident_id == incident_id)
    if status:
        statuses = [ActionStatus(s.strip()) for s in status.split(",")]
        q = q.where(Action.status.in_(statuses))
    if classification:
        classes = [ActionClassification(c.strip()) for c in classification.split(",")]
        q = q.where(Action.classification.in_(classes))
    if kind:
        kinds = [ActionKind(k.strip()) for k in kind.split(",")]
        q = q.where(Action.kind.in_(kinds))
    if since:
        since_normalized = since.replace("Z", "+00:00")
        since_dt = datetime.fromisoformat(since_normalized)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=UTC)
        q = q.where(Action.proposed_at >= since_dt)
    q = q.limit(limit + 1)

    result = await db.execute(q)
    actions = list(result.scalars().all())

    next_cursor: str | None = None
    if len(actions) > limit:
        actions = actions[:limit]
        next_cursor = str(actions[-1].id)

    items: list[ActionSummary] = []
    for act in actions:
        last_log = await _load_last_log(act.id, db)
        items.append(_action_to_summary(act, last_log))

    return ResponseList(items=items, next_cursor=next_cursor)


@router.post("", response_model=ActionProposed, status_code=201, responses={422: {"model": ErrorEnvelope}})
async def propose_response(
    body: ActionProposeIn,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> ActionProposed:
    try:
        action = await propose_action(db, body.incident_id, body.kind, body.params, ActionProposedBy.analyst)
    except OutOfLabScopeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "out_of_lab_scope", "message": exc.detail}},
        ) from exc
    await db.commit()
    await publish("action.proposed", {
        "action_id": str(action.id),
        "incident_id": str(action.incident_id),
        "kind": action.kind.value,
    })
    return ActionProposed(action=_action_to_summary(action, None))


@router.post("/{action_id}/execute", response_model=ActionExecuted, responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
async def execute_response(
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> ActionExecuted:
    actor_id = await resolve_actor_id(current_user, db)
    try:
        action, log = await execute_action(db, action_id, current_user.email, actor_user_id=actor_id)
    except ActionStateError as exc:
        status_code = 404 if exc.code == "action_not_found" else 409
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    except OutOfLabScopeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "out_of_lab_scope", "message": exc.detail}},
        ) from exc
    await db.commit()
    await publish("action.executed", {
        "action_id": str(action.id),
        "incident_id": str(action.incident_id),
        "kind": action.kind.value,
        "result": log.result.value,
    })
    if action.kind == ActionKind.request_evidence and log.result.value == "ok":
        meta = log.reversal_info or {}
        er_id = meta.get("evidence_request_id")
        if er_id:
            await publish("evidence.opened", {
                "evidence_request_id": er_id,
                "incident_id": str(action.incident_id),
                "kind": meta.get("kind", ""),
            })
    return ActionExecuted(
        action=_action_to_summary(action, log),
        log=ActionLogSummary(
            executed_at=log.executed_at,
            executed_by=log.executed_by,
            result=log.result.value,
            reason=log.reason,
            reversal_info=log.reversal_info,
            actor_user_id=log.actor_user_id,
        ),
    )


@router.post("/{action_id}/revert", response_model=ActionExecuted, responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}})
async def revert_response(
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | SystemUser = Depends(require_analyst),
) -> ActionExecuted:
    actor_id = await resolve_actor_id(current_user, db)
    try:
        action, log = await revert_action(db, action_id, current_user.email, actor_user_id=actor_id)
    except ActionStateError as exc:
        status_code = 404 if exc.code == "action_not_found" else 409
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    await db.commit()
    await publish("action.reverted", {
        "action_id": str(action.id),
        "incident_id": str(action.incident_id),
        "kind": action.kind.value,
    })
    return ActionExecuted(
        action=_action_to_summary(action, log),
        log=ActionLogSummary(
            executed_at=log.executed_at,
            executed_by=log.executed_by,
            result=log.result.value,
            reason=log.reason,
            reversal_info=log.reversal_info,
            actor_user_id=log.actor_user_id,
        ),
    )
