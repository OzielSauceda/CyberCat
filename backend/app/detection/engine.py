from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Detection, Event
from app.enums import DetectionRuleSource, Severity

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    rule_id: str
    rule_source: DetectionRuleSource
    rule_version: str
    severity_hint: Severity
    confidence_hint: Decimal
    attack_tags: list[str]
    matched_fields: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DetectorFn = Callable[[Event, AsyncSession, aioredis.Redis], Awaitable[list[DetectionResult]]]

_DETECTORS: list[DetectorFn] = []


def register(fn: DetectorFn) -> DetectorFn:
    _DETECTORS.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

async def run_detectors(
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> list[Detection]:
    fired: list[Detection] = []
    for detector in _DETECTORS:
        results = await detector(event, db, redis)
        for result in results:
            detection = Detection(
                id=uuid.uuid4(),
                event_id=event.id,
                rule_id=result.rule_id,
                rule_source=result.rule_source,
                rule_version=result.rule_version,
                severity_hint=result.severity_hint,
                confidence_hint=result.confidence_hint,
                attack_tags=result.attack_tags,
                matched_fields=result.matched_fields,
            )
            db.add(detection)
            await db.flush()
            fired.append(detection)
    return fired
