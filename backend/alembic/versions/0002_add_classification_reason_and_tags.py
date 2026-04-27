"""Add actions.classification_reason and incidents.tags

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "actions",
        sa.Column("classification_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "incidents",
        sa.Column(
            "tags",
            ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("actions", "classification_reason")
    op.drop_column("incidents", "tags")
