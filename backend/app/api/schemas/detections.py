from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.enums import Severity


class DetectionItem(BaseModel):
    id: uuid.UUID
    rule_id: str
    rule_source: Literal["sigma", "py"]
    rule_version: str
    severity_hint: Severity
    confidence_hint: Decimal
    attack_tags: list[str]
    matched_fields: dict
    event_id: uuid.UUID
    incident_id: uuid.UUID | None
    created_at: datetime


class DetectionList(BaseModel):
    items: list[DetectionItem]
    next_cursor: str | None
