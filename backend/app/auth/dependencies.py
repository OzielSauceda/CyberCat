from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import ApiToken, User, UserRole
from app.auth.security import hash_token, verify_session
from app.config import settings
from app.db.session import get_db


@dataclass
class SystemUser:
    """Sentinel returned by all auth deps when AUTH_REQUIRED=False (dev/test bypass).

    Resolves to legacy@cybercat.local for audit attribution.
    All role gates pass this through so existing tests and dev flows are unaffected.
    """

    id: uuid.UUID | None = None
    email: str = "legacy@cybercat.local"
    role: UserRole = field(default_factory=lambda: UserRole.analyst)
    token_version: int = 0
    is_active: bool = True


_LEGACY_EMAIL = "legacy@cybercat.local"


async def resolve_actor_id(user: User | SystemUser, db: AsyncSession) -> uuid.UUID | None:
    """Return the UUID to write into actor_user_id audit columns.

    Real users: their own id.
    SystemUser: the UUID of the legacy@cybercat.local sentinel row (created by migration 0007).
    """
    if isinstance(user, User):
        return user.id
    result = await db.execute(select(User).where(User.email == _LEGACY_EMAIL))
    legacy = result.scalar_one_or_none()
    return legacy.id if legacy else None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | SystemUser:
    """Core auth dependency.

    When AUTH_REQUIRED=False (default), returns SystemUser without touching the DB.
    When AUTH_REQUIRED=True, tries cookie then Bearer token, raising 401 if neither succeeds.
    """
    if not settings.auth_required:
        return SystemUser()

    # --- Cookie path (browser clients) ---
    cookie_val = request.cookies.get(settings.auth_cookie_name)
    if cookie_val:
        try:
            payload = verify_session(
                cookie_val,
                settings.auth_cookie_secret,
                settings.auth_session_ttl_minutes * 60,
            )
        except (BadSignature, SignatureExpired):
            raise HTTPException(status_code=401, detail="Session expired or invalid") from None

        try:
            user_id = uuid.UUID(payload["user_id"])
            token_version = int(payload["token_version"])
        except (KeyError, ValueError):
            raise HTTPException(status_code=401, detail="Malformed session payload") from None

        user = await db.get(User, user_id)
        if user is None or not user.is_active or user.token_version != token_version:
            raise HTTPException(status_code=401, detail="Session no longer valid")
        return user

    # --- Bearer token path (CLI / smoke scripts) ---
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw = auth_header[7:].strip()
        digest = hash_token(raw)
        result = await db.execute(
            select(ApiToken)
            .where(ApiToken.token_hash == digest, ApiToken.revoked_at.is_(None))
            .options(selectinload(ApiToken.user))
        )
        api_token = result.scalar_one_or_none()
        if api_token is None or not api_token.user.is_active:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        api_token.last_used_at = datetime.now(UTC)
        await db.commit()
        return api_token.user

    raise HTTPException(status_code=401, detail="Authentication required")


# Typed alias used as a FastAPI dependency annotation
CurrentUser = Annotated[User | SystemUser, Depends(get_current_user)]


async def require_user(user: CurrentUser) -> User | SystemUser:
    """Any authenticated user (all roles, or SystemUser dev bypass)."""
    return user


async def require_analyst(user: CurrentUser) -> User | SystemUser:
    """Analyst or admin role required; SystemUser passes through in dev bypass mode."""
    if isinstance(user, SystemUser):
        return user
    if user.role not in (UserRole.analyst, UserRole.admin):
        raise HTTPException(status_code=403, detail="Analyst or admin role required")
    return user


async def require_admin(user: CurrentUser) -> User | SystemUser:
    """Admin role required; SystemUser passes through in dev bypass mode."""
    if isinstance(user, SystemUser):
        return user
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
