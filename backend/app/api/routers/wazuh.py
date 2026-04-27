from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/wazuh", tags=["wazuh"])


class WazuhStatus(BaseModel):
    enabled: bool
    reachable: bool
    last_poll_at: datetime | None
    last_success_at: datetime | None
    lag_seconds: int | None
    events_ingested_total: int
    events_dropped_total: int
    last_error: str | None


@router.get("/status", response_model=WazuhStatus)
async def wazuh_status() -> WazuhStatus:
    if not settings.wazuh_bridge_enabled:
        return WazuhStatus(
            enabled=False,
            reachable=False,
            last_poll_at=None,
            last_success_at=None,
            lag_seconds=None,
            events_ingested_total=0,
            events_dropped_total=0,
            last_error=None,
        )

    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text(
                "SELECT last_poll_at, last_success_at, last_error,"
                " events_ingested_total, events_dropped_total"
                " FROM wazuh_cursor WHERE id = 'singleton'"
            )
        )
        cursor = row.fetchone()

    if cursor is None:
        return WazuhStatus(
            enabled=True,
            reachable=False,
            last_poll_at=None,
            last_success_at=None,
            lag_seconds=None,
            events_ingested_total=0,
            events_dropped_total=0,
            last_error="poller not yet started",
        )

    last_poll_at, last_success_at, last_error, ingested, dropped = cursor

    now = datetime.now(tz=timezone.utc)
    threshold = settings.wazuh_poll_interval_seconds * 3
    reachable = (
        last_error is None
        and last_success_at is not None
        and (now - last_success_at).total_seconds() < threshold
    )

    lag_seconds: int | None = None
    if last_success_at is not None:
        lag_seconds = int((now - last_success_at).total_seconds())

    return WazuhStatus(
        enabled=True,
        reachable=reachable,
        last_poll_at=last_poll_at,
        last_success_at=last_success_at,
        lag_seconds=lag_seconds,
        events_ingested_total=int(ingested or 0),
        events_dropped_total=int(dropped or 0),
        last_error=last_error,
    )
