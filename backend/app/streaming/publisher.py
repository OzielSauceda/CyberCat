from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from app.streaming.events import EventType, StreamEvent, topic_for

logger = logging.getLogger(__name__)

_REDIS_CHANNEL_PREFIX = "cybercat:stream:"


def _make_id() -> str:
    """Sortable unique ID for Last-Event-ID — nanosecond timestamp + random suffix."""
    ts_ns = time.time_ns()
    rand = os.urandom(4).hex()
    return f"{ts_ns:016x}{rand}"


async def publish(event_type: EventType, data: dict) -> None:
    """Publish a stream event to Redis. Redis failures are logged but never raised."""
    try:
        from app.db.redis import get_redis  # lazy import avoids circular at module load
        from app.db.redis_state import safe_redis
        topic = topic_for(event_type)
        event = StreamEvent(
            id=_make_id(),
            type=event_type,
            topic=topic,
            ts=datetime.now(UTC),
            data=data,
        )
        channel = f"{_REDIS_CHANNEL_PREFIX}{topic.value}"
        await safe_redis(
            get_redis().publish(channel, event.model_dump_json()),
            rule_id="streaming.publisher",
            op_name="publish",
            default=None,
        )
    except Exception as exc:
        logger.warning("streaming publish failed (%s): %s", event_type, exc)
