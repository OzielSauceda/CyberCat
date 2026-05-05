"""Phase 20 §C1 — incident merge/split: parent FK + 'merged' status enum value.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-05

Adds:
  - incidents.parent_incident_id (UUID, nullable, FK incidents.id, indexed)
  - 'merged' value in incident_status enum

Downgrade is intentionally asymmetric: the FK + column drop cleanly, but
Postgres < 17 cannot remove a value from an enum without a full type
rebuild (and even on 17+ it's blocked while any row references the value).
We document this and accept the floor — operationally, you only ever
downgrade a fresh DB.

See ADR-0015 for the full design discussion (junction-table alternative
rejected — n-way merges are out of scope).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Extend incident_status enum (Postgres ≥ 9.6 syntax; we target 14+)
    # IF NOT EXISTS makes this idempotent across re-runs in case a partial
    # apply ever lands.
    op.execute("ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'merged'")

    # --- 2. Add nullable FK column + index
    op.add_column(
        "incidents",
        sa.Column(
            "parent_incident_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_incidents_parent_incident_id",
        "incidents",
        "incidents",
        ["parent_incident_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_incidents_parent_incident_id",
        "incidents",
        ["parent_incident_id"],
        unique=False,
    )


def downgrade() -> None:
    # FK + column come off cleanly.
    op.drop_index("ix_incidents_parent_incident_id", table_name="incidents")
    op.drop_constraint(
        "fk_incidents_parent_incident_id", "incidents", type_="foreignkey"
    )
    op.drop_column("incidents", "parent_incident_id")
    # Intentionally NOT removing 'merged' from incident_status enum.
    # Postgres < 17: no native ALTER TYPE ... DROP VALUE — would need full
    # type rebuild (CREATE new type, ALTER all referencing columns, DROP
    # old type). Even when supported, blocked while any row uses the value.
    # Documented in ADR-0015. Operationally: only downgrade fresh DBs.
