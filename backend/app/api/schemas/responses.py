from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.api.schemas.incidents import ActionLogSummary, ActionSummary
from app.enums import ActionKind, LabAssetKind
from datetime import datetime


class ActionProposeIn(BaseModel):
    incident_id: uuid.UUID
    kind: ActionKind
    params: dict


class ActionProposed(BaseModel):
    action: ActionSummary


class ActionExecuted(BaseModel):
    action: ActionSummary
    log: ActionLogSummary


class ResponseList(BaseModel):
    items: list[ActionSummary]
    next_cursor: str | None


class LabAssetIn(BaseModel):
    kind: LabAssetKind
    natural_key: str
    notes: str | None = None


class LabAssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    natural_key: str
    registered_at: datetime
    notes: str | None
