from __future__ import annotations

import json
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlockedObservable, Event
from app.db.redis_state import safe_redis
from app.detection.engine import DetectionResult, register
from app.enums import DetectionRuleSource, Severity

RULE_ID = "py.blocked_observable_match"
_CACHE_KEY = "cybercat:blocked_observables:active"
_CACHE_TTL = 30  # seconds — short TTL so block/unblock propagates quickly

# Fields in normalized events that may carry observable values
_CHECKABLE_FIELDS = ("source_ip", "dst_ip", "src_ip", "user", "host", "image", "cmdline")


async def _get_active_values(db: AsyncSession, redis: aioredis.Redis) -> set[str]:
    # Redis cache is best-effort; on outage we fall through to the authoritative DB query.
    cached = await safe_redis(
        redis.get(_CACHE_KEY),
        rule_id=RULE_ID, op_name="get_cache", default=None,
    )
    if cached:
        return set(json.loads(cached))

    result = await db.execute(
        select(BlockedObservable.value).where(BlockedObservable.active == True)  # noqa: E712
    )
    values = {row[0] for row in result.all()}
    if values:
        await safe_redis(
            redis.set(_CACHE_KEY, json.dumps(list(values)), ex=_CACHE_TTL),
            rule_id=RULE_ID, op_name="set_cache", default=None,
        )
    return values


@register
async def blocked_observable_check(
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> list[DetectionResult]:
    active = await _get_active_values(db, redis)
    if not active:
        return []

    for field in _CHECKABLE_FIELDS:
        val = event.normalized.get(field)
        if val and str(val) in active:
            return [
                DetectionResult(
                    rule_id=RULE_ID,
                    rule_source=DetectionRuleSource.py,
                    rule_version="1.0.0",
                    severity_hint=Severity.high,
                    confidence_hint=Decimal("0.95"),
                    attack_tags=[],
                    matched_fields={"matched_field": field, "matched_value": val},
                )
            ]

    return []
