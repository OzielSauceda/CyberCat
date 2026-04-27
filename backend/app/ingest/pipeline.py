from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.correlation.auto_actions import propose_and_execute_auto_actions
from app.correlation.engine import run_correlators
from app.db.models import Event, Incident
from app.detection.engine import run_detectors
from app.enums import EventSource
from app.ingest.dedup import find_duplicate
from app.ingest.entity_extractor import extract_and_link_entities
from app.streaming.publisher import publish


@dataclass
class IngestResult:
    event_id: uuid.UUID | None
    dedup_hit: bool
    detection_ids: list[uuid.UUID]
    incident_touched: uuid.UUID | None


async def ingest_normalized_event(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    source: EventSource,
    kind: str,
    occurred_at: datetime,
    raw: dict,
    normalized: dict,
    dedupe_key: str | None,
) -> IngestResult:
    """Dedup → persist → entity extract → detect → correlate → commit → auto-actions.

    Called from both the HTTP ingest router and the Wazuh poller so both paths
    share one code path with no drift.
    """
    if dedupe_key is not None:
        existing_id = await find_duplicate(db, source, dedupe_key)
        if existing_id is not None:
            return IngestResult(
                event_id=existing_id,
                dedup_hit=True,
                detection_ids=[],
                incident_touched=None,
            )

    pipeline_start = datetime.now(timezone.utc)

    event = Event(
        id=uuid.uuid4(),
        occurred_at=occurred_at,
        source=source,
        kind=kind,
        raw=raw,
        normalized=normalized,
        dedupe_key=dedupe_key,
    )
    db.add(event)
    await db.flush()

    await extract_and_link_entities(event, db)
    detections = await run_detectors(event, db, redis)
    incident_id = await run_correlators(detections, event, db, redis)

    await db.commit()

    if incident_id is not None:
        inc = await db.get(Incident, incident_id)
        if inc is not None:
            await propose_and_execute_auto_actions(incident_id, inc.kind, db)

            # Emit incident event — created if born in this pipeline call, updated if extended
            inc_opened_at = inc.opened_at
            if inc_opened_at.tzinfo is None:
                inc_opened_at = inc_opened_at.replace(tzinfo=timezone.utc)
            is_new_incident = inc_opened_at >= pipeline_start - timedelta(seconds=2)
            if is_new_incident:
                await publish("incident.created", {
                    "incident_id": str(incident_id),
                    "kind": inc.kind.value,
                    "severity": inc.severity.value,
                })
            else:
                await publish("incident.updated", {
                    "incident_id": str(incident_id),
                    "change": "extended",
                })

    # Emit detection.fired for each detection that ran in this pipeline call
    for det in detections:
        await publish("detection.fired", {
            "detection_id": str(det.id),
            "rule_id": det.rule_id,
            "incident_id": str(incident_id) if incident_id else None,
            "severity": det.severity_hint.value if det.severity_hint else None,
        })

    return IngestResult(
        event_id=event.id,
        dedup_hit=False,
        detection_ids=[d.id for d in detections],
        incident_touched=incident_id,
    )
