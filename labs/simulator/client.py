"""Thin async HTTP wrapper for the CyberCat backend API."""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class SimulatorClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SimulatorClient":
        self._client = httpx.AsyncClient(base_url=self._base, timeout=self._timeout)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("SimulatorClient must be used as an async context manager")
        return self._client

    async def healthz(self) -> bool:
        try:
            resp = await self._c().get("/healthz")
            return resp.status_code == 200
        except Exception:
            return False

    async def register_asset(self, kind: str, natural_key: str) -> dict:
        resp = await self._c().post(
            "/v1/lab/assets",
            json={"kind": kind, "natural_key": natural_key},
        )
        if resp.status_code not in (201, 409):
            resp.raise_for_status()
        log.debug("register_asset %s:%s → %s", kind, natural_key, resp.status_code)
        return resp.json()

    async def post_event(self, payload: dict) -> dict:
        resp = await self._c().post("/v1/events/raw", json=payload)
        resp.raise_for_status()
        result = resp.json()
        log.debug(
            "post_event kind=%s → event_id=%s detections=%s incident_touched=%s",
            payload.get("kind"),
            result.get("event_id"),
            result.get("detections_fired"),
            result.get("incident_touched"),
        )
        return result

    async def get_incidents(self, limit: int = 50) -> list[dict]:
        resp = await self._c().get("/v1/incidents", params={"limit": limit})
        resp.raise_for_status()
        return resp.json().get("items", [])

    async def get_incident(self, incident_id: str) -> dict:
        resp = await self._c().get(f"/v1/incidents/{incident_id}")
        resp.raise_for_status()
        return resp.json()
