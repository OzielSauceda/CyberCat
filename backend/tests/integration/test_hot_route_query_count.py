"""Phase 19 — assert hot list-routes don't N+1.

Before A7 the `GET /v1/incidents` route fired 5 queries per incident in the page
(entity count, detection count, event count, primary user, primary host) plus
the page query itself, so a 50-item page was ~250+ queries. The same pattern
existed on `GET /v1/detections` with 1 extra query per detection.

After A7 these become a fixed number of batched queries regardless of page size.

Seeds rows directly via SQLAlchemy (not via the ingest path) so the assertion
is independent of which detectors/correlators happen to fire on synthetic events.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.models import (
    Detection,
    Entity,
    Event,
    Incident,
    IncidentDetection,
    IncidentEntity,
    IncidentEvent,
)
from app.db.session import AsyncSessionLocal
from app.enums import (
    DetectionRuleSource,
    EntityKind,
    EventEntityRole,
    EventSource,
    IncidentEntityRole,
    IncidentEventRole,
    IncidentKind,
    IncidentStatus,
    Severity,
)


async def _seed_incidents(n: int) -> None:
    """Insert N incidents with junction rows directly into the DB."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        for i in range(n):
            inc = Incident(
                id=uuid.uuid4(),
                title=f"hot-route-incident-{i}",
                kind=IncidentKind.identity_compromise,
                status=IncidentStatus.new,
                severity=Severity.medium,
                confidence=Decimal("0.50"),
                rationale="seeded for query-count test",
                summary="seed",
                tags=[],
                opened_at=now - timedelta(minutes=5 - i % 5),
                updated_at=now,
                correlator_version="1.0.0",
                correlator_rule="seed",
                dedupe_key=f"hot-route-seed-{i}",
            )
            user_ent = Entity(
                id=uuid.uuid4(),
                kind=EntityKind.user,
                natural_key=f"hot_user_{i}",
                attrs={},
                first_seen=now,
                last_seen=now,
            )
            host_ent = Entity(
                id=uuid.uuid4(),
                kind=EntityKind.host,
                natural_key=f"hot-host-{i}",
                attrs={},
                first_seen=now,
                last_seen=now,
            )
            ev = Event(
                id=uuid.uuid4(),
                occurred_at=now,
                source=EventSource.direct,
                kind="auth.failed",
                raw={},
                normalized={"user": f"hot_user_{i}", "source_ip": "203.0.113.7", "auth_type": "password"},
                dedupe_key=f"hot-route-event-{i}",
            )
            det = Detection(
                id=uuid.uuid4(),
                event_id=ev.id,
                rule_id="py.auth.failed_burst",
                rule_source=DetectionRuleSource.py,
                rule_version="1.0.0",
                severity_hint=Severity.medium,
                confidence_hint=Decimal("0.60"),
                attack_tags=["T1110"],
                matched_fields={},
            )
            # Flush parents before children so FK constraints are satisfied
            db.add_all([inc, user_ent, host_ent, ev])
            await db.flush()
            db.add(det)
            await db.flush()
            db.add_all([
                IncidentEntity(
                    incident_id=inc.id, entity_id=user_ent.id, role=IncidentEntityRole.user,
                ),
                IncidentEntity(
                    incident_id=inc.id, entity_id=host_ent.id, role=IncidentEntityRole.host,
                ),
                IncidentEvent(
                    incident_id=inc.id, event_id=ev.id, role=IncidentEventRole.trigger,
                ),
                IncidentDetection(
                    incident_id=inc.id, detection_id=det.id,
                ),
            ])
            await db.flush()
        await db.commit()


# Bound the number of queries the route should fire regardless of page size.
# - 1 page query
# - 3 batched count queries (entities, detections, events)
# - 1 batched primary user/host query
# Plus a small headroom for auth/session lookups in the request lifecycle.
_INCIDENTS_QUERY_BUDGET = 12
_DETECTIONS_QUERY_BUDGET = 10


class TestIncidentsListNoN1:
    async def test_query_count_is_bounded_for_30_page(
        self, authed_client, truncate_tables, count_queries
    ):
        await _seed_incidents(30)

        with count_queries() as counter:
            resp = await authed_client.get("/v1/incidents?limit=50")
        assert resp.status_code == 200
        n = len(resp.json()["items"])
        assert n == 30, f"expected 30 seeded incidents in page, got {n}"
        assert counter.count <= _INCIDENTS_QUERY_BUDGET, (
            f"expected ≤ {_INCIDENTS_QUERY_BUDGET} queries, got {counter.count} "
            f"for {n} incidents — N+1 regression\n"
            f"queries:\n  " + "\n  ".join(s[:120] for s in counter.statements)
        )

    async def test_query_count_does_not_grow_with_page_size(
        self, authed_client, truncate_tables, count_queries
    ):
        await _seed_incidents(30)

        with count_queries() as small:
            await authed_client.get("/v1/incidents?limit=3")
        with count_queries() as large:
            await authed_client.get("/v1/incidents?limit=50")

        # 3-item and 50-item page should fire the SAME number of queries
        # (the route is bounded in queries, not items).
        delta = large.count - small.count
        assert delta <= 1, (
            f"query count grew from {small.count} (limit=3) to {large.count} "
            f"(limit=50): delta={delta} — page size is driving query count"
        )


class TestDetectionsListNoN1:
    async def test_query_count_is_bounded(
        self, authed_client, truncate_tables, count_queries
    ):
        await _seed_incidents(30)  # also creates 30 detections + junction rows

        with count_queries() as counter:
            resp = await authed_client.get("/v1/detections?limit=50")
        assert resp.status_code == 200
        n = len(resp.json()["items"])
        assert n == 30, f"expected 30 seeded detections, got {n}"
        assert counter.count <= _DETECTIONS_QUERY_BUDGET, (
            f"expected ≤ {_DETECTIONS_QUERY_BUDGET} queries, got {counter.count} "
            f"for {n} detections — N+1 regression\n"
            f"queries:\n  " + "\n  ".join(s[:120] for s in counter.statements)
        )
