from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RawEventIn(BaseModel):
    source: Literal["direct", "seeder"]
    kind: str
    occurred_at: datetime
    raw: dict[str, Any]
    normalized: dict[str, Any]
    dedupe_key: str | None = None


class RawEventAccepted(BaseModel):
    event_id: uuid.UUID
    dedup_hit: bool
    detections_fired: list[uuid.UUID] = Field(default_factory=list)
    incident_touched: uuid.UUID | None = None


class EventSummary(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    source: str
    kind: str
    dedupe_key: str | None = None


class EventList(BaseModel):
    items: list[EventSummary]
    total: int
