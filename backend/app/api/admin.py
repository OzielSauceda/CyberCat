"""Admin endpoints — demo data lifecycle.

GET  /v1/admin/demo-status  — returns whether seeded demo data is active.
DELETE /v1/admin/demo-data  — wipes every table touched by the seed scenario
                              in a single TRUNCATE ... CASCADE transaction.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.auth.dependencies import require_admin, require_user
from app.auth.models import User
from app.auth.dependencies import SystemUser
from app.db.redis import get_redis
from app.db.session import get_db
from app.seeder import DEMO_REDIS_KEY

router = APIRouter(prefix="/admin", tags=["admin"])

# Tables wiped by DELETE /v1/admin/demo-data.
# CASCADE handles all junction tables (event_entities, incident_events,
# incident_entities, incident_detections, incident_attack, incident_transitions,
# action_logs, notes, event_entities).
# Preserved: users, api_tokens.
_TRUNCATE_SQL = text("""
TRUNCATE TABLE
    events,
    entities,
    incidents,
    detections,
    actions,
    lab_assets,
    lab_sessions,
    blocked_observables,
    evidence_requests,
    wazuh_cursor
CASCADE
""")


class DemoStatus(BaseModel):
    active: bool


@router.get("/demo-status", response_model=DemoStatus)
async def get_demo_status(
    redis: aioredis.Redis = Depends(get_redis),
    _user: User | SystemUser = Depends(require_user),
) -> DemoStatus:
    active = bool(await redis.get(DEMO_REDIS_KEY))
    return DemoStatus(active=active)


@router.delete("/demo-data", status_code=204)
async def wipe_demo_data(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _user: User | SystemUser = Depends(require_admin),
) -> None:
    try:
        await db.execute(_TRUNCATE_SQL)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Truncate failed: {exc}") from exc

    await redis.delete(DEMO_REDIS_KEY)
