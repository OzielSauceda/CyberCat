"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-19

Creates all 14 product tables, 16 PostgreSQL enum types, and their indexes.
See docs/data-model.md for the authoritative specification.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _enum(*values: str, name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name)


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Create all PostgreSQL enum types ──────────────────────────────

    _enum("user", "host", "ip", "process", "file", "observable", name="entity_kind").create(bind, checkfirst=True)
    _enum("wazuh", "direct", "seeder", name="event_source").create(bind, checkfirst=True)
    _enum(
        "actor", "target", "source_ip", "host", "process", "parent_process", "file", "observable",
        name="event_entity_role",
    ).create(bind, checkfirst=True)
    _enum("sigma", "py", name="detection_rule_source").create(bind, checkfirst=True)
    _enum("info", "low", "medium", "high", "critical", name="severity").create(bind, checkfirst=True)
    _enum(
        "identity_compromise", "endpoint_compromise", "identity_endpoint_chain", "unknown",
        name="incident_kind",
    ).create(bind, checkfirst=True)
    _enum(
        "new", "triaged", "investigating", "contained", "resolved", "closed", "reopened",
        name="incident_status",
    ).create(bind, checkfirst=True)
    _enum("trigger", "supporting", "context", name="incident_event_role").create(bind, checkfirst=True)
    _enum(
        "user", "host", "source_ip", "observable", "target_host", "target_user",
        name="incident_entity_role",
    ).create(bind, checkfirst=True)
    _enum("rule_derived", "correlator_inferred", name="attack_source").create(bind, checkfirst=True)
    _enum(
        "tag_incident", "elevate_severity", "flag_host_in_lab", "quarantine_host_lab",
        "invalidate_lab_session", "block_observable", "kill_process_lab", "request_evidence",
        name="action_kind",
    ).create(bind, checkfirst=True)
    _enum(
        "auto_safe", "suggest_only", "reversible", "disruptive",
        name="action_classification",
    ).create(bind, checkfirst=True)
    _enum("system", "analyst", name="action_proposed_by").create(bind, checkfirst=True)
    _enum("proposed", "executed", "failed", "skipped", "reverted", name="action_status").create(bind, checkfirst=True)
    _enum("ok", "fail", "skipped", name="action_result").create(bind, checkfirst=True)
    _enum("user", "host", "ip", "observable", name="lab_asset_kind").create(bind, checkfirst=True)

    # ── 2. Base tables (no FKs) ──────────────────────────────────────────

    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="entity_kind", create_type=False), nullable=False),
        sa.Column("natural_key", sa.Text(), nullable=False),
        sa.Column("attrs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_entities"),
        sa.UniqueConstraint("kind", "natural_key", name="uq_entities_kind_natural_key"),
    )
    op.create_index("ix_entities_kind_last_seen", "entities", ["kind", "last_seen"])
    op.create_index("ix_entities_attrs_gin", "entities", ["attrs"], postgresql_using="gin")

    op.create_table(
        "lab_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="lab_asset_kind", create_type=False), nullable=False),
        sa.Column("natural_key", sa.Text(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_lab_assets"),
        sa.UniqueConstraint("kind", "natural_key", name="uq_lab_assets_kind_natural_key"),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source", postgresql.ENUM(name="event_source", create_type=False), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("normalized", postgresql.JSONB(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"])
    op.create_index("ix_events_kind_occurred_at", "events", ["kind", "occurred_at"])
    op.create_index("ix_events_normalized_gin", "events", ["normalized"], postgresql_using="gin")
    op.execute(
        "CREATE UNIQUE INDEX uq_events_source_dedupe_key "
        "ON events (source, dedupe_key) WHERE dedupe_key IS NOT NULL"
    )

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="incident_kind", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="incident_status", create_type=False), nullable=False, server_default=sa.text("'new'")),
        sa.Column("severity", postgresql.ENUM(name="severity", create_type=False), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlator_version", sa.Text(), nullable=False),
        sa.Column("correlator_rule", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_incidents"),
        sa.UniqueConstraint("dedupe_key", name="uq_incidents_dedupe_key"),
    )
    op.create_index("ix_incidents_status_severity_opened", "incidents", ["status", "severity", "opened_at"])
    op.create_index("ix_incidents_updated_at", "incidents", ["updated_at"])

    # ── 3. Tables with FKs to base tables ───────────────────────────────

    op.create_table(
        "event_entities",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", postgresql.ENUM(name="event_entity_role", create_type=False), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_event_entities_event_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], name="fk_event_entities_entity_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("event_id", "entity_id", "role", name="pk_event_entities"),
    )
    op.create_index("ix_event_entities_entity_id", "event_entities", ["entity_id", "event_id"])

    op.create_table(
        "detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_source", postgresql.ENUM(name="detection_rule_source", create_type=False), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("severity_hint", postgresql.ENUM(name="severity", create_type=False), nullable=False),
        sa.Column("confidence_hint", sa.Numeric(3, 2), nullable=False),
        sa.Column("attack_tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("matched_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_detections_event_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_detections"),
    )
    op.create_index("ix_detections_rule_id_created_at", "detections", ["rule_id", "created_at"])
    op.create_index("ix_detections_event_id", "detections", ["event_id"])
    op.create_index("ix_detections_attack_tags_gin", "detections", ["attack_tags"], postgresql_using="gin")

    # ── 4. Incident junctions ────────────────────────────────────────────

    op.create_table(
        "incident_events",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", postgresql.ENUM(name="incident_event_role", create_type=False), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_incident_events_incident_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name="fk_incident_events_event_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("incident_id", "event_id", name="pk_incident_events"),
    )

    op.create_table(
        "incident_entities",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", postgresql.ENUM(name="incident_entity_role", create_type=False), nullable=False),
        sa.Column("first_seen_in_incident", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_incident_entities_incident_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], name="fk_incident_entities_entity_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("incident_id", "entity_id", "role", name="pk_incident_entities"),
    )

    op.create_table(
        "incident_detections",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_incident_detections_incident_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["detection_id"], ["detections.id"], name="fk_incident_detections_detection_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("incident_id", "detection_id", name="pk_incident_detections"),
    )

    op.create_table(
        "incident_attack",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tactic", sa.Text(), nullable=False),
        sa.Column("technique", sa.Text(), nullable=False),
        sa.Column("subtechnique", sa.Text(), nullable=True),
        sa.Column("source", postgresql.ENUM(name="attack_source", create_type=False), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_incident_attack_incident_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_incident_attack"),
    )
    op.create_index("ix_incident_attack_incident_id", "incident_attack", ["incident_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_incident_attack_combo "
        "ON incident_attack (incident_id, tactic, technique, COALESCE(subtechnique, ''))"
    )

    # ── 5. Incident transitions / response / notes ───────────────────────

    op.create_table(
        "incident_transitions",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", postgresql.ENUM(name="incident_status", create_type=False), nullable=True),
        sa.Column("to_status", postgresql.ENUM(name="incident_status", create_type=False), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_incident_transitions_incident_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_incident_transitions"),
    )
    op.create_index("ix_incident_transitions_incident_id_at", "incident_transitions", ["incident_id", "at"])

    op.create_table(
        "actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="action_kind", create_type=False), nullable=False),
        sa.Column("classification", postgresql.ENUM(name="action_classification", create_type=False), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("proposed_by", postgresql.ENUM(name="action_proposed_by", create_type=False), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", postgresql.ENUM(name="action_status", create_type=False), nullable=False, server_default=sa.text("'proposed'")),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_actions_incident_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_actions"),
    )
    op.create_index("ix_actions_incident_id", "actions", ["incident_id"])
    op.create_index("ix_actions_status", "actions", ["status"])

    op.create_table(
        "action_logs",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("executed_by", sa.Text(), nullable=False),
        sa.Column("result", postgresql.ENUM(name="action_result", create_type=False), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reversal_info", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"], name="fk_action_logs_action_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_action_logs"),
    )
    op.create_index("ix_action_logs_action_id_executed_at", "action_logs", ["action_id", "executed_at"])

    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name="fk_notes_incident_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_notes"),
    )
    op.create_index("ix_notes_incident_id_created_at", "notes", ["incident_id", "created_at"])


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop tables in reverse FK dependency order
    op.drop_table("notes")
    op.drop_table("action_logs")
    op.drop_table("actions")
    op.drop_table("incident_transitions")
    op.drop_table("incident_attack")
    op.drop_table("incident_detections")
    op.drop_table("incident_entities")
    op.drop_table("incident_events")
    op.drop_table("incidents")
    op.drop_table("detections")
    op.drop_table("event_entities")
    op.drop_table("events")
    op.drop_table("lab_assets")
    op.drop_table("entities")

    # Drop enum types
    for name in (
        "lab_asset_kind",
        "action_result",
        "action_status",
        "action_proposed_by",
        "action_classification",
        "action_kind",
        "attack_source",
        "incident_entity_role",
        "incident_event_role",
        "incident_status",
        "incident_kind",
        "severity",
        "detection_rule_source",
        "event_entity_role",
        "event_source",
        "entity_kind",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
