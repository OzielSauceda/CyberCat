from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, SystemUser, require_admin, require_user
from app.auth.models import ApiToken, User, UserRole
from app.auth.oidc import (
    _OIDC_STATE_COOKIE,
    exchange_code_for_user_info,
    get_cfg,
    make_authorization_url,
    upsert_oidc_user,
    verify_state,
)
from app.auth.security import generate_token, hash_password, sign_session, verify_password
from app.config import settings
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class MeOut(BaseModel):
    id: uuid.UUID | None = None
    email: str
    role: str
    is_active: bool
    created_at: datetime | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthConfigOut(BaseModel):
    auth_required: bool
    oidc_enabled: bool


class TokenCreateRequest(BaseModel):
    name: str


class TokenCreatedOut(BaseModel):
    id: uuid.UUID
    name: str
    token: str  # plaintext — returned exactly once; only the hash is stored
    created_at: datetime


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class RoleUpdateRequest(BaseModel):
    role: UserRole


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/config", response_model=AuthConfigOut)
async def get_auth_config() -> AuthConfigOut:
    """Public endpoint. Frontend polls this to decide whether to show the login page."""
    return AuthConfigOut(
        auth_required=settings.auth_required,
        oidc_enabled=bool(settings.oidc_provider_url),
    )


@router.post("/login", response_model=MeOut)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MeOut:
    result = await db.execute(
        select(User).where(User.email == req.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    cookie_value = sign_session(
        {
            "user_id": str(user.id),
            "role": user.role.value,
            "token_version": user.token_version,
        },
        settings.auth_cookie_secret,
    )
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=cookie_value,
        max_age=settings.auth_session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )
    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(settings.auth_cookie_name)
    return {"ok": True}


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser) -> MeOut:
    if isinstance(user, SystemUser):
        return MeOut(email=user.email, role=user.role.value, is_active=True)
    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/tokens", response_model=TokenCreatedOut, status_code=201)
async def create_token(
    req: TokenCreateRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TokenCreatedOut:
    if isinstance(user, SystemUser):
        raise HTTPException(
            status_code=400,
            detail="Token creation requires a real user account. Use the CLI: python -m app.cli issue-token",
        )
    plaintext, digest = generate_token()
    api_token = ApiToken(user_id=user.id, name=req.name, token_hash=digest)
    db.add(api_token)
    await db.commit()
    await db.refresh(api_token)
    return TokenCreatedOut(
        id=api_token.id,
        name=api_token.name,
        token=plaintext,
        created_at=api_token.created_at,
    )


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[TokenOut]:
    if isinstance(user, SystemUser):
        return []
    result = await db.execute(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at)
    )
    return [TokenOut.model_validate(t) for t in result.scalars().all()]


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    api_token = await db.get(ApiToken, token_id)
    if api_token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    if not isinstance(user, SystemUser):
        if user.role != UserRole.admin and api_token.user_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot revoke another user's token")
    if api_token.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Token already revoked")
    api_token.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: Annotated[object, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    result = await db.execute(select(User).order_by(User.created_at))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: uuid.UUID,
    req: RoleUpdateRequest,
    _: Annotated[object, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = req.role
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# OIDC endpoints (Phase 14.4)
# ---------------------------------------------------------------------------


@router.get("/oidc/login", include_in_schema=True)
async def oidc_login(request: Request) -> RedirectResponse:
    """Redirect the browser to the OIDC provider's authorization endpoint.

    Sets a short-lived signed cookie (10 min) that carries the state + nonce
    for CSRF protection.  Returns HTTP 501 when OIDC is not configured.
    """
    cfg = get_cfg(request)
    auth_url, signed_state = make_authorization_url(cfg)

    redirect = RedirectResponse(url=auth_url, status_code=302)
    redirect.set_cookie(
        key=_OIDC_STATE_COOKIE,
        value=signed_state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )
    return redirect


@router.get("/oidc/callback", include_in_schema=True)
async def oidc_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle the OIDC provider callback.

    Verifies state, exchanges the authorization code for tokens, validates the
    ID token, JIT-provisions the user (role=read_only if new), and sets the
    session cookie before redirecting to ``/``.
    """
    cfg = get_cfg(request)

    code = request.query_params.get("code")
    state_param = request.query_params.get("state")
    if not code or not state_param:
        raise HTTPException(status_code=400, detail="Missing code or state in OIDC callback")

    cookie_val = request.cookies.get(_OIDC_STATE_COOKIE)
    if not cookie_val:
        raise HTTPException(status_code=400, detail="Missing OIDC state cookie")

    nonce = verify_state(cookie_val, state_param)
    oidc_subject, email = await exchange_code_for_user_info(cfg, code, nonce)
    user = await upsert_oidc_user(db, oidc_subject=oidc_subject, email=email)

    session_cookie = sign_session(
        {
            "user_id": str(user.id),
            "role": user.role.value,
            "token_version": user.token_version,
        },
        settings.auth_cookie_secret,
    )

    redirect = RedirectResponse(url="/", status_code=302)
    redirect.set_cookie(
        key=settings.auth_cookie_name,
        value=session_cookie,
        max_age=settings.auth_session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )
    redirect.delete_cookie(_OIDC_STATE_COOKIE)
    return redirect
