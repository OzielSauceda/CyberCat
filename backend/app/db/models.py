from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import (
    ActionClassification,
    ActionKind,
    ActionProposedBy,
    ActionResult,
    ActionStatus,
    AttackSource,
    BlockableKind,
    DetectionRuleSource,
    EntityKind,
    EventEntityRole,
    EventSource,
    EvidenceKind,
    EvidenceStatus,
    IncidentEntityRole,
    IncidentEventRole,
    IncidentKind,
    IncidentStatus,
    LabAssetKind,
    Severity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enum(py_enum: type, name: str) -> sa.Enum:
    return sa.Enum(py_enum, name=name, create_type=False)


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[EntityKind] = mapped_column(_enum(EntityKind, "entity_kind"), nullable=False)
    natural_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    first_seen: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("kind", "natural_key", name="uq_entities_kind_natural_key"),
        Index("ix_entities_kind_last_seen", "kind", "last_seen"),
        Index("ix_entities_attrs_gin", "attrs", postgresql_using="gin"),
    )


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    source: Mapped[EventSource] = mapped_column(_enum(EventSource, "event_source"), nullable=False)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        Index("ix_events_occurred_at", "occurred_at"),
        Index("ix_events_kind_occurred_at", "kind", "occurred_at"),
        Index("ix_events_normalized_gin", "normalized", postgresql_using="gin"),
        # Partial unique index: enforced in migration via op.execute; declared here for documentation.
        # uq_events_source_dedupe_key: UNIQUE (source, dedupe_key) WHERE dedupe_key IS NOT NULL
    )


# ---------------------------------------------------------------------------
# event_entities  (junction)
# ---------------------------------------------------------------------------

class EventEntity(Base):
    __tablename__ = "event_entities"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[EventEntityRole] = mapped_column(
        _enum(EventEntityRole, "event_entity_role"), primary_key=True
    )

    __table_args__ = (
        Index("ix_event_entities_entity_id", "entity_id", "event_id"),
    )


# ---------------------------------------------------------------------------
# detections
# ---------------------------------------------------------------------------

class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    rule_source: Mapped[DetectionRuleSource] = mapped_column(
        _enum(DetectionRuleSource, "detection_rule_source"), nullable=False
    )
    rule_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    severity_hint: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), nullable=False)
    confidence_hint: Mapped[Decimal] = mapped_column(sa.Numeric(3, 2), nullable=False)
    attack_tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    matched_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_detections_rule_id_created_at", "rule_id", "created_at"),
        Index("ix_detections_event_id", "event_id"),
        Index("ix_detections_attack_tags_gin", "attack_tags", postgresql_using="gin"),
    )


# ---------------------------------------------------------------------------
# incidents
# ---------------------------------------------------------------------------

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    kind: Mapped[IncidentKind] = mapped_column(_enum(IncidentKind, "incident_kind"), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        _enum(IncidentStatus, "incident_status"),
        nullable=False,
        server_default=text("'new'"),
    )
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(sa.Numeric(3, 2), nullable=False)
    rationale: Mapped[str] = mapped_column(sa.Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False, server_default=text("'{}'"))
    opened_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    correlator_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    correlator_rule: Mapped[str] = mapped_column(sa.Text, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Phase 20 §C — set when this incident has been merged INTO another.
    # Self-referential nullable FK. Split children do NOT set this (per
    # ADR-0015 — splits use IncidentTransition rows for the audit link).
    parent_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_incidents_dedupe_key"),
        Index("ix_incidents_status_severity_opened", "status", "severity", "opened_at"),
        Index("ix_incidents_updated_at", "updated_at"),
        Index("ix_incidents_parent_incident_id", "parent_incident_id"),
    )


# ---------------------------------------------------------------------------
# incident_events  (junction)
# ---------------------------------------------------------------------------

class IncidentEvent(Base):
    __tablename__ = "incident_events"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[IncidentEventRole] = mapped_column(
        _enum(IncidentEventRole, "incident_event_role"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# ---------------------------------------------------------------------------
# incident_entities  (junction)
# ---------------------------------------------------------------------------

class IncidentEntity(Base):
    __tablename__ = "incident_entities"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[IncidentEntityRole] = mapped_column(
        _enum(IncidentEntityRole, "incident_entity_role"), primary_key=True
    )
    first_seen_in_incident: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# ---------------------------------------------------------------------------
# incident_detections  (junction)
# ---------------------------------------------------------------------------

class IncidentDetection(Base):
    __tablename__ = "incident_detections"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    detection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("detections.id", ondelete="RESTRICT"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# ---------------------------------------------------------------------------
# incident_attack  (junction — surrogate PK, expression unique index in migration)
# ---------------------------------------------------------------------------

class IncidentAttack(Base):
    __tablename__ = "incident_attack"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    tactic: Mapped[str] = mapped_column(sa.Text, nullable=False)
    technique: Mapped[str] = mapped_column(sa.Text, nullable=False)
    subtechnique: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    source: Mapped[AttackSource] = mapped_column(_enum(AttackSource, "attack_source"), nullable=False)

    __table_args__ = (
        Index("ix_incident_attack_incident_id", "incident_id"),
        # Expression unique index created via op.execute in migration:
        # UNIQUE (incident_id, tactic, technique, COALESCE(subtechnique, ''))
    )


# ---------------------------------------------------------------------------
# incident_transitions
# ---------------------------------------------------------------------------

class IncidentTransition(Base):
    __tablename__ = "incident_transitions"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[IncidentStatus | None] = mapped_column(
        _enum(IncidentStatus, "incident_status"), nullable=True
    )
    to_status: Mapped[IncidentStatus] = mapped_column(
        _enum(IncidentStatus, "incident_status"), nullable=False
    )
    actor: Mapped[str] = mapped_column(sa.Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Phase 14: nullable FK; populated once auth is active; kept denormalized `actor` string too
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_incident_transitions_incident_id_at", "incident_id", "at"),
    )


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------

class Action(Base):
    __tablename__ = "actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[ActionKind] = mapped_column(_enum(ActionKind, "action_kind"), nullable=False)
    classification: Mapped[ActionClassification] = mapped_column(
        _enum(ActionClassification, "action_classification"), nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposed_by: Mapped[ActionProposedBy] = mapped_column(
        _enum(ActionProposedBy, "action_proposed_by"), nullable=False
    )
    proposed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    status: Mapped[ActionStatus] = mapped_column(
        _enum(ActionStatus, "action_status"),
        nullable=False,
        server_default=text("'proposed'"),
    )
    classification_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        Index("ix_actions_incident_id", "incident_id"),
        Index("ix_actions_status", "status"),
    )


# ---------------------------------------------------------------------------
# action_logs
# ---------------------------------------------------------------------------

class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    executed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    executed_by: Mapped[str] = mapped_column(sa.Text, nullable=False)
    result: Mapped[ActionResult] = mapped_column(_enum(ActionResult, "action_result"), nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reversal_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Phase 14: nullable FK; denormalized `executed_by` string is kept permanently
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_action_logs_action_id_executed_at", "action_id", "executed_at"),
    )


# ---------------------------------------------------------------------------
# lab_assets
# ---------------------------------------------------------------------------

class LabAsset(Base):
    __tablename__ = "lab_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[LabAssetKind] = mapped_column(_enum(LabAssetKind, "lab_asset_kind"), nullable=False)
    natural_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Phase 14: who registered this asset (nullable for pre-auth rows)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("kind", "natural_key", name="uq_lab_assets_kind_natural_key"),
    )


# ---------------------------------------------------------------------------
# wazuh_cursor  (singleton poller state)
# ---------------------------------------------------------------------------

class WazuhCursor(Base):
    __tablename__ = "wazuh_cursor"

    id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    search_after: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    events_ingested_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=text("0")
    )
    events_dropped_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=text("0")
    )


# ---------------------------------------------------------------------------
# lab_sessions
# ---------------------------------------------------------------------------

class LabSession(Base):
    __tablename__ = "lab_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False
    )
    host_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    invalidated_by_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actions.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_lab_sessions_user_host", "user_entity_id", "host_entity_id"),
        Index("ix_lab_sessions_invalidated", "invalidated_at"),
    )


# ---------------------------------------------------------------------------
# blocked_observables
# ---------------------------------------------------------------------------

class BlockedObservable(Base):
    __tablename__ = "blocked_observables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[BlockableKind] = mapped_column(_enum(BlockableKind, "blockable_kind"), nullable=False)
    value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    blocked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    blocked_by_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actions.id", ondelete="RESTRICT"), nullable=False
    )
    active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        Index("ix_blocked_observables_active_kind_value", "active", "kind", "value"),
    )


# ---------------------------------------------------------------------------
# evidence_requests
# ---------------------------------------------------------------------------

class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    target_host_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[EvidenceKind] = mapped_column(_enum(EvidenceKind, "evidence_kind"), nullable=False)
    status: Mapped[EvidenceStatus] = mapped_column(
        _enum(EvidenceStatus, "evidence_status"),
        nullable=False,
        server_default=text("'open'"),
    )
    requested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    collected_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    payload_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Phase 14: audit FKs (nullable for pre-auth rows)
    collected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_evidence_requests_incident_id", "incident_id"),
        Index("ix_evidence_requests_status", "status"),
    )


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)
    author: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Phase 14: nullable FK; denormalized `author` string is kept permanently
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_notes_incident_id_created_at", "incident_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Auth models (Phase 14) — imported here so Alembic autogen picks them up
# ---------------------------------------------------------------------------
from app.auth.models import ApiToken, User  # noqa: E402, F401
