from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.detection.engine import DetectionResult, register
from app.enums import DetectionRuleSource, Severity

RULE_ID = "py.auth.anomalous_source_success"
_LOOKBACK_DAYS = 7


@register
async def auth_anomalous_source_success(
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> list[DetectionResult]:
    if event.kind != "auth.succeeded":
        return []

    user: str | None = event.normalized.get("user")
    source_ip: str | None = event.normalized.get("source_ip")
    if not user or not source_ip:
        return []

    # Require recent failures for this user to still be in the window
    window_key = f"corr:auth_failures:{user}"
    failure_count_raw = await redis.get(window_key)
    if not failure_count_raw or int(failure_count_raw) < 1:
        return []

    # Check if this source_ip has ever succeeded for this user in the last 7 days
    lookback_start = event.occurred_at - timedelta(days=_LOOKBACK_DAYS)
    result = await db.execute(
        select(func.count(Event.id)).where(
            Event.kind == "auth.succeeded",
            Event.occurred_at >= lookback_start,
            Event.occurred_at < event.occurred_at,
            Event.normalized["user"].astext == user,
            Event.normalized["source_ip"].astext == source_ip,
        )
    )
    prior_successes = result.scalar_one()
    if prior_successes > 0:
        return []

    failure_count = int(failure_count_raw)
    return [DetectionResult(
        rule_id=RULE_ID,
        rule_source=DetectionRuleSource.py,
        rule_version="1.0.0",
        severity_hint=Severity.high,
        confidence_hint=Decimal("0.70"),
        attack_tags=["T1078", "T1078.002"],
        matched_fields={
            "user": user,
            "source_ip": source_ip,
            "prior_failures_in_window": failure_count,
        },
    )]
