from __future__ import annotations

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 60
_redis_client = None


def _build_client() -> httpx.AsyncClient:
    # Wazuh manager REST API (port 55000) uses its own internal Wazuh-signed cert,
    # not our custom CA. Skip verification for manager connections in the lab.
    return httpx.AsyncClient(verify=False, timeout=10.0)


async def agent_id_for_host(host: str) -> str | None:
    """Return the Wazuh agent_id for the given host natural_key, or None if not enrolled."""
    import redis.asyncio as aioredis

    cache_key = f"cybercat:wazuh_agent:{host}"

    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        cached = await r.get(cache_key)
        if cached is not None:
            await r.aclose()
            data = json.loads(cached)
            return data.get("agent_id")
    except Exception as exc:
        logger.debug("agent_lookup redis read failed: %s", exc)

    try:
        async with _build_client() as client:
            # Authenticate to get a token for the query
            from app.response.dispatchers.wazuh_ar import _authenticate
            token = await _authenticate(client)
            url = f"{settings.wazuh_manager_url.rstrip('/')}/agents"
            resp = await client.get(
                url,
                params={"name": host},
                headers={"Authorization": f"Bearer {token}"},
            )
            if not resp.is_success:
                logger.warning("agent_lookup HTTP %s for host %r", resp.status_code, host)
                return None

            data = resp.json()
            agents = data.get("data", {}).get("affected_items", [])
            if not agents:
                return None

            agent_id: str = str(agents[0]["id"])

            try:
                r2 = aioredis.from_url(settings.redis_url, decode_responses=True)
                await r2.set(cache_key, json.dumps({"agent_id": agent_id}), ex=_CACHE_TTL_S)
                await r2.aclose()
            except Exception as exc:
                logger.debug("agent_lookup redis write failed: %s", exc)

            return agent_id

    except Exception as exc:
        logger.warning("agent_lookup error for host %r: %s", host, exc)
        return None
