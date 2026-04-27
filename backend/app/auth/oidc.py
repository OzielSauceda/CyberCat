"""OIDC opt-in support (Phase 14.4).

Lazy-initialized: `discover_oidc()` is called once at startup and the result
is stored on `app.state.oidc`.  All endpoints call `get_cfg(request)` which
raises HTTP 501 when OIDC is not configured, so the rest of the codebase does
not need to guard against None.

State/nonce are stored in a signed, short-lived cookie (itsdangerous) so the
backend stays stateless — no Redis or DB write required for the OAuth dance.
"""
from __future__ import annotations

import secrets
import urllib.parse
from dataclasses import dataclass

import httpx
from authlib.jose import JsonWebKey, JsonWebToken, KeySet  # type: ignore[attr-defined]
from authlib.jose.errors import JoseError  # type: ignore[attr-defined]
from fastapi import HTTPException, Request
from itsdangerous import BadData, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.config import settings

# Accepted signing algorithms.  RS256/ES256 cover Google, Okta, Auth0, Keycloak,
# Authentik.  The wider list handles edge-case deployments.
_JWT = JsonWebToken(["RS256", "ES256", "RS384", "RS512", "PS256"])

_OIDC_STATE_COOKIE = "cybercat_oidc_state"
_FALLBACK_STATE_SECRET = "cybercat-oidc-dev-state-fallback"


@dataclass
class OIDCConfig:
    """Cached OIDC discovery metadata and JWKS fetched at startup."""

    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks: KeySet


async def discover_oidc() -> OIDCConfig | None:
    """Fetch OIDC discovery document + JWKS.  Returns None if not configured."""
    if not settings.oidc_provider_url:
        return None

    missing = [
        name.upper()
        for name in ("oidc_client_id", "oidc_client_secret", "oidc_redirect_uri")
        if not getattr(settings, name)
    ]
    if missing:
        raise RuntimeError(
            f"OIDC_PROVIDER_URL is set but the following vars are missing: {', '.join(missing)}"
        )

    base = settings.oidc_provider_url.rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        disco_resp = await client.get(f"{base}/.well-known/openid-configuration")
        disco_resp.raise_for_status()
        disco = disco_resp.json()

        jwks_resp = await client.get(disco["jwks_uri"])
        jwks_resp.raise_for_status()
        jwks = JsonWebKey.import_key_set(jwks_resp.json())

    return OIDCConfig(
        authorization_endpoint=disco["authorization_endpoint"],
        token_endpoint=disco["token_endpoint"],
        userinfo_endpoint=disco.get("userinfo_endpoint"),
        jwks=jwks,
    )


# ---------------------------------------------------------------------------
# State cookie helpers
# ---------------------------------------------------------------------------


def _state_signer() -> URLSafeSerializer:
    secret = settings.auth_cookie_secret or _FALLBACK_STATE_SECRET
    return URLSafeSerializer(secret, salt="cybercat-oidc-state")


def get_cfg(request: Request) -> OIDCConfig:
    """Return the cached OIDCConfig or raise HTTP 501 if OIDC is not configured."""
    cfg: OIDCConfig | None = getattr(request.app.state, "oidc", None)
    if cfg is None:
        raise HTTPException(status_code=501, detail="OIDC is not configured on this server")
    return cfg


def make_authorization_url(cfg: OIDCConfig) -> tuple[str, str]:
    """Build the provider authorization URL.

    Returns ``(url, signed_state_cookie_value)``.
    The signed cookie embeds both state and nonce so the callback can verify both
    without any server-side session storage.
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    signed = _state_signer().dumps({"state": state, "nonce": nonce})

    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
    )
    return f"{cfg.authorization_endpoint}?{params}", signed


def verify_state(cookie_value: str, state_param: str) -> str:
    """Verify the OIDC state cookie and return the stored nonce.

    Raises HTTP 400 on any mismatch or tampering.
    """
    try:
        stored = _state_signer().loads(cookie_value)
    except BadData as exc:
        raise HTTPException(
            status_code=400, detail="Invalid or expired OIDC state cookie"
        ) from exc

    if stored.get("state") != state_param:
        raise HTTPException(status_code=400, detail="OIDC state mismatch — possible CSRF")

    return stored["nonce"]


# ---------------------------------------------------------------------------
# Token exchange + ID-token validation
# ---------------------------------------------------------------------------


async def exchange_code_for_user_info(
    cfg: OIDCConfig, code: str, nonce: str
) -> tuple[str, str]:
    """Exchange authorization code for tokens; return ``(oidc_subject, email)``.

    Validates the ID token signature and nonce.  Falls back to the userinfo
    endpoint if ``email`` is absent from the ID token claims.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            cfg.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
        )

    if token_resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="Token exchange with OIDC provider failed")

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="OIDC provider did not return an id_token")

    try:
        claims = _JWT.decode(id_token, cfg.jwks)
        claims.validate()
    except JoseError as exc:
        raise HTTPException(
            status_code=401, detail=f"ID token validation failed: {exc}"
        ) from exc

    if claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="ID token nonce mismatch")

    oidc_subject: str = claims["sub"]
    email: str | None = claims.get("email")

    if not email and cfg.userinfo_endpoint:
        access_token = token_data.get("access_token", "")
        async with httpx.AsyncClient(timeout=10.0) as client:
            ui_resp = await client.get(
                cfg.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            email = ui_resp.json().get("email")

    if not email:
        raise HTTPException(
            status_code=502, detail="Could not obtain email from OIDC provider"
        )

    return oidc_subject, email


# ---------------------------------------------------------------------------
# JIT user provisioning
# ---------------------------------------------------------------------------


async def upsert_oidc_user(
    db: AsyncSession, oidc_subject: str, email: str
) -> User:
    """Find or JIT-provision a User for an OIDC login.

    Lookup order:
    1. By ``oidc_subject`` — returning user's existing account.
    2. By ``email`` — links a local password account to this OIDC subject.
    3. Create a new account with ``role=read_only`` (admin elevates via CLI or PATCH).
    """
    result = await db.execute(select(User).where(User.oidc_subject == oidc_subject))
    user = result.scalar_one_or_none()
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        return user

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        user.oidc_subject = oidc_subject
        await db.commit()
        await db.refresh(user)
        return user

    user = User(
        email=email,
        oidc_subject=oidc_subject,
        role=UserRole.read_only,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
