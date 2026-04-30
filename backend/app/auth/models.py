from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    read_only = "read_only"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # email is declared as Text here; the migration creates it as CITEXT for case-insensitive uniqueness
    email: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(sa.Text, nullable=True, unique=True)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="user_role", create_type=False),
        nullable=False,
        server_default=text("'read_only'"),
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=text("true"))
    token_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    api_tokens: Mapped[list[ApiToken]] = relationship("ApiToken", back_populates="user", lazy="select")

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index(
            "ix_users_oidc_subject",
            "oidc_subject",
            postgresql_where=text("oidc_subject IS NOT NULL"),
        ),
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # sha256 digest of the plaintext token; only this value is ever persisted
    token_hash: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False, unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="api_tokens")

    __table_args__ = (Index("ix_api_tokens_token_hash", "token_hash"),)
