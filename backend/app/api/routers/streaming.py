from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import SystemUser, require_user
from app.auth.models import User
from app.streaming.bus import EventBus, get_bus
from app.streaming.events import StreamEvent, Topic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])

_ALL_TOPICS = frozenset(Topic)
_HB_INTERVAL = 20.0  # seconds between heartbeat comments


@router.get("", summary="SSE event stream")
async def sse_stream(
    topics: Annotated[
        str | None,
        Query(description="Comma-separated topic filter, e.g. incidents,actions"),
    ] = None,
    _user: User | SystemUser = Depends(require_user),
) -> StreamingResponse:
    if topics is not None:
        try:
            topic_filter = frozenset(Topic(t.strip()) for t in topics.split(",") if t.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid topic: {exc}") from exc
        if not topic_filter:
            topic_filter = _ALL_TOPICS
    else:
        topic_filter = _ALL_TOPICS

    bus = get_bus()
    return StreamingResponse(
        _generate(bus, topic_filter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _generate(
    bus: EventBus,
    topic_filter: frozenset[Topic],
) -> AsyncGenerator[str, None]:
    q = bus.register()
    try:
        while True:
            try:
                raw: str = await asyncio.wait_for(q.get(), timeout=_HB_INTERVAL)
            except TimeoutError:
                yield ": hb\n\n"
                continue

            try:
                event = StreamEvent.model_validate_json(raw)
            except Exception as exc:
                logger.warning("invalid stream event dropped: %s", exc)
                continue

            if event.topic not in topic_filter:
                continue

            data_json = json.dumps(event.data)
            yield f"id: {event.id}\nevent: {event.type}\ndata: {data_json}\n\n"
    except asyncio.CancelledError:
        pass
    except GeneratorExit:
        pass
    finally:
        bus.unregister(q)
