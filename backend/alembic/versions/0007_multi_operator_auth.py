"""Multi-operator auth: users, api_tokens, audit FKs, legacy backfill (Phase 14.1)

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Stable UUID for the legacy sentinel user; referenced during backfill
_LEGACY_UUID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # citext provides case-insensitive text comparisons used for email uniqueness
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'read_only')")

    op.execute(
        """
        CREATE TABLE users (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            email       CITEXT      NOT NULL,
            password_hash TEXT,
            oidc_subject  TEXT,
            role        user_role   NOT NULL DEFAULT 'read_only',
            is_active   BOOLEAN     NOT NULL DEFAULT true,
            token_version INTEGER   NOT NULL DEFAULT 1,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            UNIQUE (email),
            UNIQUE (oidc_subject)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE api_tokens (
            id           UUID        NOT NULL DEFAULT gen_random_uuid(),
            user_id      UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name         TEXT        NOT NULL,
            token_hash   BYTEA       NOT NULL,
            last_used_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at   TIMESTAMPTZ,
            PRIMARY KEY (id),
            UNIQUE (token_hash)
        )
        """
    )

    op.execute("CREATE INDEX ix_users_email ON users(email)")
    op.execute(
        "CREATE INDEX ix_users_oidc_subject ON users(oidc_subject) WHERE oidc_subject IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_api_tokens_token_hash ON api_tokens(token_hash)")

    # Nullable FK columns on audit tables (existing rows will be backfilled below;
    # new rows are populated by the application once auth is active)
    op.execute(
        "ALTER TABLE incident_transitions ADD COLUMN actor_user_id UUID"
        "    REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE action_logs ADD COLUMN actor_user_id UUID"
        "    REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE notes ADD COLUMN actor_user_id UUID"
        "    REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE evidence_requests ADD COLUMN collected_by_user_id UUID"
        "    REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE evidence_requests ADD COLUMN dismissed_by_user_id UUID"
        "    REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE lab_assets ADD COLUMN created_by_user_id UUID"
        "    REFERENCES users(id) ON DELETE SET NULL"
    )

    # Insert the legacy sentinel user (is_active=false — not a real login account)
    op.execute(
        f"""
        INSERT INTO users (id, email, role, is_active, token_version, created_at)
        VALUES ('{_LEGACY_UUID}', 'legacy@cybercat.local', 'analyst', false, 1, now())
        """
    )

    # Backfill existing audit rows to the legacy sentinel so FKs are coherent
    op.execute(f"UPDATE incident_transitions SET actor_user_id = '{_LEGACY_UUID}'")
    op.execute(f"UPDATE action_logs         SET actor_user_id = '{_LEGACY_UUID}'")
    op.execute(f"UPDATE notes               SET actor_user_id = '{_LEGACY_UUID}'")


def downgrade() -> None:
    # Drop FK columns first (implicitly drops FK constraints)
    op.execute("ALTER TABLE lab_assets          DROP COLUMN IF EXISTS created_by_user_id")
    op.execute("ALTER TABLE evidence_requests   DROP COLUMN IF EXISTS dismissed_by_user_id")
    op.execute("ALTER TABLE evidence_requests   DROP COLUMN IF EXISTS collected_by_user_id")
    op.execute("ALTER TABLE notes               DROP COLUMN IF EXISTS actor_user_id")
    op.execute("ALTER TABLE action_logs         DROP COLUMN IF EXISTS actor_user_id")
    op.execute("ALTER TABLE incident_transitions DROP COLUMN IF EXISTS actor_user_id")

    op.execute("DROP TABLE IF EXISTS api_tokens")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TYPE  IF EXISTS user_role")
    # citext extension is intentionally not dropped: other extensions/tables may depend on it
