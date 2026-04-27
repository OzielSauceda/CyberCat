"""Preseed lab_assets for the identity-compromise scenario

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-20

Inserts the three assets used by labs/smoke_test_phase3.sh and labs/smoke_test_phase5.sh.
ON CONFLICT DO NOTHING makes this safe to re-run against a DB that already has rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO lab_assets (id, kind, natural_key, notes, registered_at)
        VALUES
            (gen_random_uuid(), 'user', 'alice@corp.local',
             'Lab identity — identity-compromise scenario', now()),
            (gen_random_uuid(), 'host', 'lab-win10-01',
             'Primary Windows lab endpoint', now()),
            (gen_random_uuid(), 'ip',   '203.0.113.7',
             'Scripted adversary source IP used in smoke tests', now())
        ON CONFLICT (kind, natural_key) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM lab_assets
        WHERE (kind, natural_key) IN (
            ('user', 'alice@corp.local'),
            ('host', 'lab-win10-01'),
            ('ip',   '203.0.113.7')
        )
    """))
