from __future__ import annotations

from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.detection.engine import DetectionResult, register
from app.enums import DetectionRuleSource, Severity

RULE_ID = "py.auth.failed_burst"
_WINDOW_SEC = 60
_THRESHOLD = 4
_COOLDOWN_SEC = 120


@register
async def auth_failed_burst(
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> list[DetectionResult]:
    if event.kind != "auth.failed":
        return []

    user: str | None = event.normalized.get("user")
    if not user:
        return []

    cooldown_key = f"corr:rule_cooldown:{RULE_ID}:{user}"
    if await redis.exists(cooldown_key):
        return []

    window_key = f"corr:auth_failures:{user}"
    count = await redis.incr(window_key)
    if count == 1:
        await redis.expire(window_key, _WINDOW_SEC)

    if count >= _THRESHOLD:
        await redis.set(cooldown_key, "1", ex=_COOLDOWN_SEC)
        return [DetectionResult(
            rule_id=RULE_ID,
            rule_source=DetectionRuleSource.py,
            rule_version="1.0.0",
            severity_hint=Severity.medium,
            confidence_hint=Decimal("0.60"),
            attack_tags=["T1110", "T1110.003"],
            matched_fields={"count": count, "window_sec": _WINDOW_SEC, "user": user},
        )]

    return []
