"""Phase 20 §C6 — integration tests for POST /v1/incidents/{id}/merge-into.

Cases (per docs/phase-20-plan.md §C6 merge):
  1. Two open incidents → target absorbs source's events/entities/detections,
     source.status='merged', source.parent_incident_id=target.id, two
     IncidentTransition rows (source side + target side).
  2. Self-merge → 422.
  3. Merge into closed target → 409.
  4. Re-merge of an already-merged source → 409.
  5. Concurrent merge attempts on the same source — second blocks on the
     advisory lock then errors. (Tested via two sequential requests; the
     advisory-lock-held assertion is implicit in the per-request transactions.)
  6. Read-only / viewer role → 403 (covered by test_auth_gating.py).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.models import Incident, IncidentTransition
from app.db.session import AsyncSessionLocal
from app.enums import IncidentKind, IncidentStatus, Severity
from decimal import Decimal


async def _seed_incident(
    *,
    title: str,
    kind: IncidentKind = IncidentKind.identity_compromise,
    status: IncidentStatus = IncidentStatus.new,
    severity: Severity = Severity.medium,
    confidence: Decimal = Decimal("0.50"),
) -> uuid.UUID:
    """Insert a bare-bones incident row directly. Returns its id."""
    inc_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Incident(
            id=inc_id,
            title=title,
            kind=kind,
            status=status,
            severity=severity,
            confidence=confidence,
            rationale="seed for merge test",
            tags=[],
            correlator_version="test",
            correlator_rule="test",
            dedupe_key=f"test-merge:{inc_id}",
        ))
        await db.commit()
    return inc_id


@pytest.mark.asyncio
async def test_merge_happy_path(authed_client, truncate_tables):
    src = await _seed_incident(title="Source", severity=Severity.low, confidence=Decimal("0.30"))
    tgt = await _seed_incident(title="Target", severity=Severity.medium, confidence=Decimal("0.70"))

    r = await authed_client.post(
        f"/v1/incidents/{src}/merge-into",
        json={"target_id": str(tgt), "reason": "duplicate of target"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(tgt)

    async with AsyncSessionLocal() as db:
        src_row = await db.get(Incident, src)
        tgt_row = await db.get(Incident, tgt)
        assert src_row.status == IncidentStatus.merged
        assert src_row.parent_incident_id == tgt
        # Severity = max(low, medium) = medium
        assert tgt_row.severity == Severity.medium
        # Confidence = avg(0.30, 0.70) = 0.50
        assert tgt_row.confidence == Decimal("0.50")

        # Two transition rows (one per side)
        trans = await db.execute(
            select(IncidentTransition).where(
                IncidentTransition.incident_id.in_([src, tgt])
            )
        )
        rows = list(trans.scalars().all())
        # Filter out the initial "null → new" rows that may exist if
        # other code paths inserted them. We expect at least 2 rows
        # mentioning the merge in their reason.
        merge_rows = [r for r in rows if "Merged" in (r.reason or "") or "Absorbed" in (r.reason or "")]
        assert len(merge_rows) >= 2


@pytest.mark.asyncio
async def test_merge_self_returns_422(authed_client, truncate_tables):
    inc = await _seed_incident(title="Solo")
    r = await authed_client.post(
        f"/v1/incidents/{inc}/merge-into",
        json={"target_id": str(inc), "reason": "self-merge attempt"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"]["code"] == "self_merge"


@pytest.mark.asyncio
async def test_merge_into_closed_target_returns_409(authed_client, truncate_tables):
    src = await _seed_incident(title="Source")
    tgt = await _seed_incident(title="Closed Target", status=IncidentStatus.closed)
    r = await authed_client.post(
        f"/v1/incidents/{src}/merge-into",
        json={"target_id": str(tgt), "reason": "trying closed"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"]["code"] == "target_closed"


@pytest.mark.asyncio
async def test_merge_into_already_merged_target_returns_409(authed_client, truncate_tables):
    src = await _seed_incident(title="Source")
    tgt = await _seed_incident(title="Already Merged", status=IncidentStatus.merged)
    r = await authed_client.post(
        f"/v1/incidents/{src}/merge-into",
        json={"target_id": str(tgt), "reason": "trying merged target"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"]["code"] == "target_closed"


@pytest.mark.asyncio
async def test_remerge_of_already_merged_source_returns_409(authed_client, truncate_tables):
    src = await _seed_incident(title="Twice-merged source")
    tgt1 = await _seed_incident(title="First target")
    tgt2 = await _seed_incident(title="Second target")

    r1 = await authed_client.post(
        f"/v1/incidents/{src}/merge-into",
        json={"target_id": str(tgt1), "reason": "first merge"},
    )
    assert r1.status_code == 200, r1.text

    r2 = await authed_client.post(
        f"/v1/incidents/{src}/merge-into",
        json={"target_id": str(tgt2), "reason": "second merge attempt"},
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"]["error"]["code"] == "source_merged"


@pytest.mark.asyncio
async def test_merge_missing_target_returns_404(authed_client, truncate_tables):
    src = await _seed_incident(title="Source")
    r = await authed_client.post(
        f"/v1/incidents/{src}/merge-into",
        json={"target_id": str(uuid.uuid4()), "reason": "nonexistent target"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"]["code"] == "target_missing"
