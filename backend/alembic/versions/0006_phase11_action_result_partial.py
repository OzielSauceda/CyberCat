"""Add partial value to actionresult and actionstatus enums (Phase 11)

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE action_result ADD VALUE IF NOT EXISTS 'partial'")
    op.execute("ALTER TYPE action_status ADD VALUE IF NOT EXISTS 'partial'")


def downgrade() -> None:
    # Postgres does not support removing enum values without a full table rewrite.
    # Downgrade is intentionally a no-op; remove rows with status='partial' manually
    # before rolling back if needed.
    pass
