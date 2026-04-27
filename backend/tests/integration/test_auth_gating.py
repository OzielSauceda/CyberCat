"""Canonical gate inventory — every analyst-gated mutation route must appear here.

Purpose:
  - 401: anonymous requests are rejected when auth is required.
  - 403: read_only role is rejected on analyst-gated routes.

Adding a new mutation route without updating ANALYST_ROUTES will NOT fail these tests
automatically, but the list serves as the authoritative inventory for review and CI audits.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import UserRole
from app.db.redis import close_redis, init_redis
from app.main import app
from app.streaming.bus import close_bus, init_bus


@dataclass
class _ReadOnlyUser:
    """Non-SystemUser with read_only role; causes require_analyst to raise 403."""
    id: uuid.UUID = field(default_factory=lambda: uuid.UUID("00000000-0000-0000-0000-000000000099"))
    email: str = "readonly@gating-test.local"
    role: UserRole = field(default_factory=lambda: UserRole.read_only)
    is_active: bool = True
    token_version: int = 1


async def _raise_401() -> None:
    raise HTTPException(status_code=401, detail="Authentication required")


async def _return_readonly() -> _ReadOnlyUser:
    return _ReadOnlyUser()


# ── Canonical mutation-route inventory ────────────────────────────────────────
# Each entry: (HTTP method, path).  Paths with IDs use a fixed UUID so the route
# matches even though the row won't exist — the auth check fires before the DB hit.
_FIXED_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

ANALYST_ROUTES = [
    ("POST",   "/v1/responses"),
    ("POST",   f"/v1/responses/{_FIXED_ID}/execute"),
    ("POST",   f"/v1/responses/{_FIXED_ID}/revert"),
    ("POST",   f"/v1/incidents/{_FIXED_ID}/transitions"),
    ("POST",   f"/v1/incidents/{_FIXED_ID}/notes"),
    ("POST",   f"/v1/evidence-requests/{_FIXED_ID}/collect"),
    ("POST",   f"/v1/evidence-requests/{_FIXED_ID}/dismiss"),
    ("POST",   "/v1/lab/assets"),
    ("DELETE", f"/v1/lab/assets/{_FIXED_ID}"),
    ("POST",   "/v1/events/raw"),
]
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def _anon_client():
    """Client where get_current_user raises 401 (simulates unauthenticated access)."""
    app.dependency_overrides[get_current_user] = _raise_401
    await init_redis()
    await init_bus()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_bus()
    await close_redis()
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture()
async def _ro_client():
    """Client where get_current_user returns a non-SystemUser with read_only role."""
    app.dependency_overrides[get_current_user] = _return_readonly
    await init_redis()
    await init_bus()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_bus()
    await close_redis()
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("method,path", ANALYST_ROUTES)
@pytest.mark.asyncio
async def test_mutation_returns_401_for_anonymous(_anon_client: AsyncClient, method: str, path: str) -> None:
    """Each mutation route must reject unauthenticated requests with 401."""
    response = await _anon_client.request(method, path)
    assert response.status_code == 401, (
        f"{method} {path} → expected 401 for anonymous, got {response.status_code}"
    )


@pytest.mark.parametrize("method,path", ANALYST_ROUTES)
@pytest.mark.asyncio
async def test_mutation_returns_403_for_readonly(_ro_client: AsyncClient, method: str, path: str) -> None:
    """Each analyst-gated route must reject read_only role with 403."""
    response = await _ro_client.request(method, path)
    assert response.status_code == 403, (
        f"{method} {path} → expected 403 for read_only, got {response.status_code}"
    )
