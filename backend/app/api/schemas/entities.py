from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.enums import EntityKind, IncidentKind, IncidentStatus, Severity


class EntityTimelineEvent(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    kind: str
    normalized: dict


class EntityIncidentSummary(BaseModel):
    id: uuid.UUID
    title: str
    kind: IncidentKind
    status: IncidentStatus
    severity: Severity
    confidence: Decimal
    opened_at: datetime
    updated_at: datetime


class EntityDetail(BaseModel):
    id: uuid.UUID
    kind: EntityKind
    natural_key: str
    attrs: dict
    first_seen: datetime
    last_seen: datetime
    recent_events: list[EntityTimelineEvent]
    related_incidents: list[EntityIncidentSummary]
