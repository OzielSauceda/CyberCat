"""Integration tests for the auth router (Phase 14.1).

Tests cover:
- Public config endpoint
- /me in dev-bypass mode (AUTH_REQUIRED=False default)
- Login / logout / /me with a committed test user and AUTH_REQUIRED patched to True
- Bearer token auth
- Admin-only endpoints in dev-bypass mode (SystemUser passes)
- Role enforcement when AUTH_REQUIRED=True

Requires: docker compose stack (Postgres + Redis).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.auth.models import ApiToken, User, UserRole
from app.auth.security import hash_password
from app.config import settings
from app.db.session import AsyncSessionLocal

_TEST_SECRET = "test-cookie-secret-must-be-long-enough!"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(client: AsyncClient):
    """Commit a real admin user; clean up after the test."""
    email = f"integ_admin_{uuid.uuid4().hex[:8]}@test.local"
    user_id: uuid.UUID | None = None

    async with AsyncSessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password("admin-pass-123"),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    yield {"id": user_id, "email": email, "password": "admin-pass-123"}

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ApiToken).where(ApiToken.user_id == user_id))
        for t in result.scalars().all():
            await db.delete(t)
        u = await db.get(User, user_id)
        if u:
            await db.delete(u)
        await db.commit()


@pytest_asyncio.fixture
async def readonly_user(client: AsyncClient):
    """Commit a read_only user; clean up after the test."""
    email = f"integ_ro_{uuid.uuid4().hex[:8]}@test.local"
    user_id: uuid.UUID | None = None

    async with AsyncSessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password("ro-pass-123"),
            role=UserRole.read_only,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    yield {"id": user_id, "email": email, "password": "ro-pass-123"}

    async with AsyncSessionLocal() as db:
        u = await db.get(User, user_id)
        if u:
            await db.delete(u)
        await db.commit()


# ---------------------------------------------------------------------------
# Public endpoint — always available
# ---------------------------------------------------------------------------


async def test_auth_config_returns_expected_fields(client: AsyncClient) -> None:
    resp = await client.get("/v1/auth/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_required"] is False
    assert data["oidc_enabled"] is False


# ---------------------------------------------------------------------------
# Dev-bypass mode (AUTH_REQUIRED=False, the default)
# ---------------------------------------------------------------------------


async def test_me_dev_bypass_returns_legacy_user(client: AsyncClient) -> None:
    resp = await client.get("/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "legacy@cybercat.local"
    assert data["role"] == "analyst"


async def test_logout_always_succeeds(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_list_users_dev_bypass_returns_200(client: AsyncClient) -> None:
    """Admin endpoint returns 200 in dev bypass mode — SystemUser passes require_admin."""
    resp = await client.get("/v1/auth/users")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_create_token_dev_bypass_returns_400(client: AsyncClient) -> None:
    """Token creation is explicitly blocked for SystemUser (no real user_id to associate)."""
    resp = await client.post("/v1/auth/tokens", json={"name": "test"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Login / logout / me with AUTH_REQUIRED=True
# ---------------------------------------------------------------------------


async def test_login_valid_credentials(
    client: AsyncClient,
    admin_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    resp = await client.post(
        "/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == admin_user["email"]
    assert data["role"] == "admin"
    assert settings.auth_cookie_name in resp.cookies


async def test_login_wrong_password_returns_401(
    client: AsyncClient,
    admin_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    resp = await client.post(
        "/v1/auth/login",
        json={"email": admin_user["email"], "password": "totally-wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    resp = await client.post(
        "/v1/auth/login",
        json={"email": "nobody@example.com", "password": "any"},
    )
    assert resp.status_code == 401


async def test_me_with_valid_session_cookie(
    client: AsyncClient,
    admin_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert login_resp.status_code == 200

    me_resp = await client.get("/v1/auth/me", cookies=login_resp.cookies)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == admin_user["email"]


async def test_me_without_auth_returns_401_when_required(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    resp = await client.get("/v1/auth/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bearer token auth
# ---------------------------------------------------------------------------


async def test_bearer_token_auth(
    client: AsyncClient,
    admin_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    # Create a token while logged in via cookie
    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    token_resp = await client.post(
        "/v1/auth/tokens",
        json={"name": "test-bearer"},
        cookies=login_resp.cookies,
    )
    assert token_resp.status_code == 201
    plaintext = token_resp.json()["token"]
    assert plaintext.startswith("cct_")

    # Use the plaintext token as Bearer to call /me
    me_resp = await client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == admin_user["email"]


async def test_revoke_own_token(
    client: AsyncClient,
    admin_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    token_resp = await client.post(
        "/v1/auth/tokens",
        json={"name": "revoke-me"},
        cookies=login_resp.cookies,
    )
    token_id = token_resp.json()["id"]
    plaintext = token_resp.json()["token"]

    revoke_resp = await client.delete(
        f"/v1/auth/tokens/{token_id}",
        cookies=login_resp.cookies,
    )
    assert revoke_resp.status_code == 204

    # Use a fresh client with no session cookie to confirm the bearer token is dead
    from httpx import ASGITransport, AsyncClient as FreshClient
    from app.main import app as _app
    async with FreshClient(transport=ASGITransport(app=_app), base_url="http://test") as bare:
        me_resp = await bare.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {plaintext}"},
        )
    assert me_resp.status_code == 401


# ---------------------------------------------------------------------------
# Role enforcement on admin endpoints
# ---------------------------------------------------------------------------


async def test_list_users_requires_admin_role(
    client: AsyncClient,
    readonly_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": readonly_user["email"], "password": readonly_user["password"]},
    )
    assert login_resp.status_code == 200

    resp = await client.get("/v1/auth/users", cookies=login_resp.cookies)
    assert resp.status_code == 403


async def test_update_role_requires_admin(
    client: AsyncClient,
    readonly_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": readonly_user["email"], "password": readonly_user["password"]},
    )
    resp = await client.patch(
        f"/v1/auth/users/{readonly_user['id']}/role",
        json={"role": "analyst"},
        cookies=login_resp.cookies,
    )
    assert resp.status_code == 403


async def test_admin_can_update_role(
    client: AsyncClient,
    admin_user: dict,
    readonly_user: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_cookie_secret", _TEST_SECRET)

    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    resp = await client.patch(
        f"/v1/auth/users/{readonly_user['id']}/role",
        json={"role": "analyst"},
        cookies=login_resp.cookies,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "analyst"
