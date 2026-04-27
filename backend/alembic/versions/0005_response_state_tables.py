"""Add response state tables: lab_sessions, blocked_observables, evidence_requests

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lab_sessions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_entity_id",
            UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "host_entity_id",
            UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "invalidated_by_action_id",
            UUID(as_uuid=False),
            sa.ForeignKey("actions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_lab_sessions_user_host", "lab_sessions", ["user_entity_id", "host_entity_id"])
    op.create_index("ix_lab_sessions_invalidated", "lab_sessions", ["invalidated_at"])

    op.create_table(
        "blocked_observables",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "kind",
            sa.Enum("ip", "domain", "hash", "file", name="blockable_kind"),
            nullable=False,
        ),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "blocked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "blocked_by_action_id",
            UUID(as_uuid=False),
            sa.ForeignKey("actions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "ix_blocked_observables_active_kind_value",
        "blocked_observables",
        ["active", "kind", "value"],
    )

    op.create_table(
        "evidence_requests",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "incident_id",
            UUID(as_uuid=False),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_host_entity_id",
            UUID(as_uuid=False),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "triage_log",
                "process_list",
                "network_connections",
                "memory_snapshot",
                name="evidence_kind",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("open", "collected", "dismissed", name="evidence_status"),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_url", sa.Text, nullable=True),
    )
    op.create_index("ix_evidence_requests_incident_id", "evidence_requests", ["incident_id"])
    op.create_index("ix_evidence_requests_status", "evidence_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_evidence_requests_status", "evidence_requests")
    op.drop_index("ix_evidence_requests_incident_id", "evidence_requests")
    op.drop_table("evidence_requests")

    op.drop_index("ix_blocked_observables_active_kind_value", "blocked_observables")
    op.drop_table("blocked_observables")

    op.drop_index("ix_lab_sessions_invalidated", "lab_sessions")
    op.drop_index("ix_lab_sessions_user_host", "lab_sessions")
    op.drop_table("lab_sessions")

    op.execute("DROP TYPE IF EXISTS evidence_status")
    op.execute("DROP TYPE IF EXISTS evidence_kind")
    op.execute("DROP TYPE IF EXISTS blockable_kind")
