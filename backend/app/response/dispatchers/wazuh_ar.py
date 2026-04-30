from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token cache — module-level, reused across requests
# ---------------------------------------------------------------------------

_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}
_TOKEN_LIFETIME_S = 270  # re-auth before the Wazuh 5-min JWT window closes


@dataclass
class DispatchResult:
    status: str  # "dispatched" | "failed" | "skipped" | "disabled"
    wazuh_command_id: str | None = None
    response: dict | None = None
    error: str | None = None


def _build_client() -> httpx.AsyncClient:
    # Wazuh manager REST API (port 55000) uses its own internal Wazuh-signed cert,
    # not our custom CA. Skip verification for manager connections in the lab.
    read_s = float(settings.wazuh_ar_timeout_seconds)
    return httpx.AsyncClient(
        verify=False,
        timeout=httpx.Timeout(read_s, connect=5.0),
    )


async def _authenticate(client: httpx.AsyncClient) -> str:
    now = time.monotonic()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]  # type: ignore[return-value]

    url = f"{settings.wazuh_manager_url.rstrip('/')}/security/user/authenticate"
    resp = await client.post(
        url,
        auth=(settings.wazuh_manager_user, settings.wazuh_manager_password),
    )
    resp.raise_for_status()
    token = resp.json()["data"]["token"]
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + _TOKEN_LIFETIME_S
    return token  # type: ignore[return-value]


async def dispatch_ar(
    command: str,
    agent_id: str,
    arguments: list[str],
    alert: dict | None = None,
) -> DispatchResult:
    if not settings.wazuh_ar_enabled:
        return DispatchResult(status="disabled")

    try:
        async with _build_client() as client:
            token = await _authenticate(client)
            url = f"{settings.wazuh_manager_url.rstrip('/')}/active-response"
            payload: dict[str, Any] = {"command": command, "arguments": arguments}
            if alert:
                payload["alert"] = alert

            headers = {"Authorization": f"Bearer {token}"}
            # Agent filter is a query parameter, not a body field
            resp = await client.put(url, json=payload, headers=headers, params={"agents_list": agent_id})

            if resp.status_code == 401:
                # Token expired — invalidate cache and retry once
                _token_cache["token"] = None
                _token_cache["expires_at"] = 0.0
                token = await _authenticate(client)
                headers = {"Authorization": f"Bearer {token}"}
                resp = await client.put(url, json=payload, headers=headers, params={"agents_list": agent_id})

            body: dict = {}
            try:
                body = resp.json()
            except Exception:
                pass

            if resp.is_success:
                # Wazuh returns HTTP 200 even for partial errors (e.g. code 1652).
                # Check the body for actual delivery confirmation.
                affected = body.get("data", {}).get("total_affected_items", 0) if body else 0
                if affected < 1:
                    err_items = body.get("data", {}).get("failed_items", []) if body else []
                    err_msg = err_items[0]["error"]["message"] if err_items else "no agents affected"
                    return DispatchResult(status="failed", response=body, error=err_msg)
                cmd_id = body.get("data", {}).get("id") if body else None
                return DispatchResult(
                    status="dispatched",
                    wazuh_command_id=str(cmd_id) if cmd_id else None,
                    response=body,
                )
            return DispatchResult(
                status="failed",
                response=body,
                error=f"HTTP {resp.status_code}",
            )

    except httpx.TimeoutException as exc:
        logger.warning("wazuh_ar dispatch timeout: %s", exc)
        return DispatchResult(status="failed", error=f"timeout: {exc}")
    except Exception as exc:
        logger.warning("wazuh_ar dispatch error: %s", exc)
        return DispatchResult(status="failed", error=str(exc))
