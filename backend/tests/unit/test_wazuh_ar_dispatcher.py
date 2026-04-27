"""Unit tests for the Wazuh AR dispatcher — all network calls mocked."""
from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.response.dispatchers import wazuh_ar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, body: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.is_success = status_code < 400
    r.json.return_value = body
    r.raise_for_status = MagicMock()
    return r


# ---------------------------------------------------------------------------
# Short-circuit: AR disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_disabled(monkeypatch):
    monkeypatch.setattr("app.response.dispatchers.wazuh_ar.settings", MagicMock(wazuh_ar_enabled=False))
    result = await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])
    assert result.status == "disabled"
    assert result.wazuh_command_id is None


# ---------------------------------------------------------------------------
# Auth: success + token cache reuse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_success_and_cache(monkeypatch):
    mock_settings = MagicMock(
        wazuh_ar_enabled=True,
        wazuh_manager_url="https://wazuh:55000",
        wazuh_manager_user="wui",
        wazuh_manager_password="pass",
        wazuh_ar_timeout_seconds=10,
        wazuh_ca_bundle_path="/nonexistent/ca.pem",
    )
    monkeypatch.setattr("app.response.dispatchers.wazuh_ar.settings", mock_settings)

    # Reset cache
    wazuh_ar._token_cache["token"] = None
    wazuh_ar._token_cache["expires_at"] = 0.0

    auth_resp = _make_response(200, {"data": {"token": "tok123"}})
    dispatch_resp = _make_response(200, {"data": {"id": "ar-1", "total_affected_items": 1, "affected_items": ["001"]}})

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=auth_resp)
    client_mock.put = AsyncMock(return_value=dispatch_resp)
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("app.response.dispatchers.wazuh_ar._build_client", return_value=client_mock):
        result = await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])

    assert result.status == "dispatched"
    assert result.wazuh_command_id == "ar-1"
    # Token should be cached now
    assert wazuh_ar._token_cache["token"] == "tok123"

    # Second call — auth should NOT be called again (cache hit)
    wazuh_ar._token_cache["expires_at"] = time.monotonic() + 999
    client_mock2 = AsyncMock()
    client_mock2.post = AsyncMock(return_value=auth_resp)
    client_mock2.put = AsyncMock(return_value=dispatch_resp)
    client_mock2.__aenter__ = AsyncMock(return_value=client_mock2)
    client_mock2.__aexit__ = AsyncMock(return_value=False)

    with patch("app.response.dispatchers.wazuh_ar._build_client", return_value=client_mock2):
        await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])

    client_mock2.post.assert_not_called()


# ---------------------------------------------------------------------------
# Auth 401 → re-auth once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_401_reauth(monkeypatch):
    mock_settings = MagicMock(
        wazuh_ar_enabled=True,
        wazuh_manager_url="https://wazuh:55000",
        wazuh_manager_user="wui",
        wazuh_manager_password="pass",
        wazuh_ar_timeout_seconds=10,
        wazuh_ca_bundle_path="/nonexistent/ca.pem",
    )
    monkeypatch.setattr("app.response.dispatchers.wazuh_ar.settings", mock_settings)
    wazuh_ar._token_cache["token"] = "stale"
    wazuh_ar._token_cache["expires_at"] = time.monotonic() + 999

    auth_resp = _make_response(200, {"data": {"token": "fresh"}})
    first_put = _make_response(401, {})
    first_put.is_success = False
    second_put = _make_response(200, {"data": {"id": "ar-2", "total_affected_items": 1, "affected_items": ["001"]}})

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=auth_resp)
    client_mock.put = AsyncMock(side_effect=[first_put, second_put])
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("app.response.dispatchers.wazuh_ar._build_client", return_value=client_mock):
        result = await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])

    assert result.status == "dispatched"
    assert client_mock.post.call_count == 1  # re-authed once


# ---------------------------------------------------------------------------
# Dispatch 5xx → failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_5xx(monkeypatch):
    mock_settings = MagicMock(
        wazuh_ar_enabled=True,
        wazuh_manager_url="https://wazuh:55000",
        wazuh_manager_user="wui",
        wazuh_manager_password="pass",
        wazuh_ar_timeout_seconds=10,
        wazuh_ca_bundle_path="/nonexistent/ca.pem",
    )
    monkeypatch.setattr("app.response.dispatchers.wazuh_ar.settings", mock_settings)
    wazuh_ar._token_cache["token"] = None
    wazuh_ar._token_cache["expires_at"] = 0.0

    auth_resp = _make_response(200, {"data": {"token": "tok"}})
    fail_resp = _make_response(503, {"error": "unavailable"})

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=auth_resp)
    client_mock.put = AsyncMock(return_value=fail_resp)
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("app.response.dispatchers.wazuh_ar._build_client", return_value=client_mock):
        result = await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])

    assert result.status == "failed"
    assert "503" in result.error


# ---------------------------------------------------------------------------
# Dispatch timeout → failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_timeout(monkeypatch):
    import httpx

    mock_settings = MagicMock(
        wazuh_ar_enabled=True,
        wazuh_manager_url="https://wazuh:55000",
        wazuh_manager_user="wui",
        wazuh_manager_password="pass",
        wazuh_ar_timeout_seconds=10,
        wazuh_ca_bundle_path="/nonexistent/ca.pem",
    )
    monkeypatch.setattr("app.response.dispatchers.wazuh_ar.settings", mock_settings)
    wazuh_ar._token_cache["token"] = None
    wazuh_ar._token_cache["expires_at"] = 0.0

    auth_resp = _make_response(200, {"data": {"token": "tok"}})

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=auth_resp)
    client_mock.put = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("app.response.dispatchers.wazuh_ar._build_client", return_value=client_mock):
        result = await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])

    assert result.status == "failed"
    assert "timeout" in result.error


# ---------------------------------------------------------------------------
# Authorization header must not appear in log output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_header_not_logged(monkeypatch, caplog):
    mock_settings = MagicMock(
        wazuh_ar_enabled=True,
        wazuh_manager_url="https://wazuh:55000",
        wazuh_manager_user="wui",
        wazuh_manager_password="pass",
        wazuh_ar_timeout_seconds=10,
        wazuh_ca_bundle_path="/nonexistent/ca.pem",
    )
    monkeypatch.setattr("app.response.dispatchers.wazuh_ar.settings", mock_settings)
    wazuh_ar._token_cache["token"] = None
    wazuh_ar._token_cache["expires_at"] = 0.0

    auth_resp = _make_response(200, {"data": {"token": "SUPERSECRETTOKEN"}})
    fail_resp = _make_response(500, {})

    client_mock = AsyncMock()
    client_mock.post = AsyncMock(return_value=auth_resp)
    client_mock.put = AsyncMock(return_value=fail_resp)
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with caplog.at_level(logging.DEBUG, logger="app.response.dispatchers.wazuh_ar"):
        with patch("app.response.dispatchers.wazuh_ar._build_client", return_value=client_mock):
            await wazuh_ar.dispatch_ar("firewall-drop0", "001", ["1.2.3.4"])

    for record in caplog.records:
        assert "Authorization" not in record.getMessage(), (
            f"Authorization header leaked in log: {record.getMessage()}"
        )
        assert "SUPERSECRETTOKEN" not in record.getMessage()
