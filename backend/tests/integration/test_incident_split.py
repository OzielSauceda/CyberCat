"""Phase 20 §C6 — integration tests for POST /v1/incidents/{id}/split.

Cases (per docs/phase-20-plan.md §C6 split):
  1. Split N events from incident with M total → child has N rows; source
     has M-N; both have transition rows.
  2. Empty event_ids AND empty entity_ids → 422.
  3. Events not belonging to source → 422.
  4. Split of merged incident → 422.
  5. Split of closed incident → 422.
  6. Read-only / viewer role → 403 (covered by test_auth_gating.py).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import (
    Entity,
    Event,
    Incident,
    IncidentEntity,
    IncidentEvent,
)
from app.db.session import AsyncSessionLocal
from app.enums import (
    EntityKind,
    EventSource,
    IncidentEntityRole,
    IncidentEventRole,
    IncidentKind,
    IncidentStatus,
    Severity,
)


async def _seed_incident_with_events(
    *,
    title: str,
    n_events: int,
    status: IncidentStatus = IncidentStatus.new,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Insert an incident + N events linked as triggers. Returns (incident_id, event_ids)."""
    inc_id = uuid.uuid4()
    event_ids: list[uuid.UUID] = []
    async with AsyncSessionLocal() as db:
        db.add(Incident(
            id=inc_id,
            title=title,
            kind=IncidentKind.endpoint_compromise,
            status=status,
            severity=Severity.medium,
            confidence=Decimal("0.50"),
            rationale="seed for split test",
            tags=[],
            correlator_version="test",
            correlator_rule="test",
            dedupe_key=f"test-split:{inc_id}",
        ))
        await db.flush()

        from datetime import UTC, datetime
        now = datetime.now(UTC)
        for i in range(n_events):
            evt_id = uuid.uuid4()
            event_ids.append(evt_id)
            db.add(Event(
                id=evt_id,
                source=EventSource.seeder,
                kind="process.created",
                occurred_at=now,
                raw={},
                normalized={
                    "host": "test-host",
                    "pid": 1000 + i,
                    "ppid": 1,
                    "image": f"/bin/test-{i}",
                    "cmdline": f"test-{i}",
                },
                dedupe_key=f"test-split-evt:{inc_id}:{i}",
            ))
            db.add(IncidentEvent(
                incident_id=inc_id,
                event_id=evt_id,
                role=IncidentEventRole.context,
            ))
        await db.commit()
    return inc_id, event_ids


@pytest.mark.asyncio
async def test_split_happy_path_moves_n_events(authed_client, truncate_tables):
    src, evts = await _seed_incident_with_events(title="Source", n_events=5)
    moving = evts[:2]

    r = await authed_client.post(
        f"/v1/incidents/{src}/split",
        json={
            "event_ids": [str(e) for e in moving],
            "entity_ids": [],
            "reason": "these belong to a different incident",
        },
    )
    assert r.status_code == 201, r.text
    child_id = uuid.UUID(r.json()["id"])

    async with AsyncSessionLocal() as db:
        src_count = await db.execute(
            select(IncidentEvent).where(IncidentEvent.incident_id == src)
        )
        src_event_rows = list(src_count.scalars().all())
        child_count = await db.execute(
            select(IncidentEvent).where(IncidentEvent.incident_id == child_id)
        )
        child_event_rows = list(child_count.scalars().all())

        assert len(src_event_rows) == 3, f"source kept {len(src_event_rows)}, expected 3"
        assert len(child_event_rows) == 2, f"child got {len(child_event_rows)}, expected 2"

        # Moved events are NOT on source
        moved_set = {e for e in moving}
        src_set = {ie.event_id for ie in src_event_rows}
        assert not (moved_set & src_set), "moved events still attached to source"
        # Moved events ARE on child
        child_set = {ie.event_id for ie in child_event_rows}
        assert moved_set == child_set


@pytest.mark.asyncio
async def test_split_empty_selection_returns_422(authed_client, truncate_tables):
    src, _ = await _seed_incident_with_events(title="Source", n_events=2)
    r = await authed_client.post(
        f"/v1/incidents/{src}/split",
        json={"event_ids": [], "entity_ids": [], "reason": "empty"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"]["code"] == "empty_selection"


@pytest.mark.asyncio
async def test_split_event_not_in_source_returns_422(authed_client, truncate_tables):
    src, _ = await _seed_incident_with_events(title="Source", n_events=2)
    fake = uuid.uuid4()
    r = await authed_client.post(
        f"/v1/incidents/{src}/split",
        json={"event_ids": [str(fake)], "entity_ids": [], "reason": "stranger event"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"]["code"] == "events_not_in_source"


@pytest.mark.asyncio
async def test_split_of_merged_returns_422(authed_client, truncate_tables):
    src, evts = await _seed_incident_with_events(
        title="Already merged", n_events=3, status=IncidentStatus.merged,
    )
    r = await authed_client.post(
        f"/v1/incidents/{src}/split",
        json={
            "event_ids": [str(evts[0])],
            "entity_ids": [],
            "reason": "split a merged thing",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"]["code"] == "source_closed"


@pytest.mark.asyncio
async def test_split_of_closed_returns_422(authed_client, truncate_tables):
    src, evts = await _seed_incident_with_events(
        title="Closed", n_events=3, status=IncidentStatus.closed,
    )
    r = await authed_client.post(
        f"/v1/incidents/{src}/split",
        json={
            "event_ids": [str(evts[0])],
            "entity_ids": [],
            "reason": "split a closed thing",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"]["code"] == "source_closed"


@pytest.mark.asyncio
async def test_split_missing_source_returns_404(authed_client, truncate_tables):
    r = await authed_client.post(
        f"/v1/incidents/{uuid.uuid4()}/split",
        json={"event_ids": [str(uuid.uuid4())], "entity_ids": [], "reason": "nope"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"]["code"] == "source_missing"
