from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.enums import (
    EntityKind,
    IncidentKind,
    IncidentStatus,
    Severity,
)


class IncidentSummary(BaseModel):
    id: uuid.UUID
    title: str
    kind: IncidentKind
    status: IncidentStatus
    severity: Severity
    confidence: Decimal
    opened_at: datetime
    updated_at: datetime
    entity_count: int
    detection_count: int
    event_count: int
    primary_user: str | None
    primary_host: str | None


class IncidentList(BaseModel):
    items: list[IncidentSummary]
    next_cursor: str | None


class EntityRef(BaseModel):
    id: uuid.UUID
    kind: EntityKind
    natural_key: str
    attrs: dict
    role_in_incident: str


class DetectionRef(BaseModel):
    id: uuid.UUID
    rule_id: str
    rule_source: Literal["sigma", "py"]
    rule_version: str
    severity_hint: Severity
    confidence_hint: Decimal
    attack_tags: list[str]
    matched_fields: dict
    event_id: uuid.UUID
    created_at: datetime


class TimelineEvent(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    kind: str
    source: Literal["wazuh", "direct", "seeder"]
    normalized: dict
    role_in_incident: Literal["trigger", "supporting", "context"]
    entity_ids: list[uuid.UUID]


class AttackRef(BaseModel):
    tactic: str
    technique: str
    subtechnique: str | None
    source: Literal["rule_derived", "correlator_inferred"]


class ActionLogSummary(BaseModel):
    executed_at: datetime
    executed_by: str
    result: Literal["ok", "fail", "skipped", "partial"]
    reason: str | None
    reversal_info: dict | None
    actor_user_id: uuid.UUID | None = None


class ActionSummary(BaseModel):
    id: uuid.UUID
    kind: str
    classification: Literal["auto_safe", "suggest_only", "reversible", "disruptive"]
    classification_reason: str | None
    status: Literal["proposed", "executed", "failed", "skipped", "reverted", "partial"]
    params: dict
    proposed_by: Literal["system", "analyst"]
    proposed_at: datetime
    last_log: ActionLogSummary | None


class TransitionRef(BaseModel):
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    actor: str
    reason: str | None
    at: datetime
    actor_user_id: uuid.UUID | None = None


class NoteRef(BaseModel):
    id: uuid.UUID
    body: str
    author: str
    created_at: datetime
    actor_user_id: uuid.UUID | None = None


class TransitionIn(BaseModel):
    to_status: IncidentStatus
    reason: str | None = None


class TransitionOut(BaseModel):
    incident_id: uuid.UUID
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    at: datetime


class NoteIn(BaseModel):
    body: str


class IncidentDetail(BaseModel):
    id: uuid.UUID
    title: str
    kind: IncidentKind
    status: IncidentStatus
    severity: Severity
    confidence: Decimal
    rationale: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    correlator_rule: str
    correlator_version: str

    entities: list[EntityRef]
    detections: list[DetectionRef]
    timeline: list[TimelineEvent]
    attack: list[AttackRef]
    actions: list[ActionSummary]
    transitions: list[TransitionRef]
    notes: list[NoteRef]
