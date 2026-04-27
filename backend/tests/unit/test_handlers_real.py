"""Unit tests for Phase 9A real response handlers.

These tests run against the live Postgres+Redis stack (docker compose up -d).
Each test provisions minimal DB fixtures and calls the handler functions directly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.db.models import (
    Action,
    ActionLog,
    Entity,
    EvidenceRequest,
    Incident,
    LabAsset,
    LabSession,
)
from app.enums import (
    ActionClassification,
    ActionKind,
    ActionProposedBy,
    ActionResult,
    ActionStatus,
    BlockableKind,
    EntityKind,
    EvidenceKind,
    EvidenceStatus,
    IncidentKind,
    IncidentStatus,
    LabAssetKind,
    Severity,
)
from app.response.handlers import (
    block_observable,
    invalidate_session,
    kill_process,
    quarantine_host,
    request_evidence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_incident(db_session) -> Incident:
    inc = Incident(
        id=uuid.uuid4(),
        title="Test incident",
        kind=IncidentKind.identity_compromise,
        status=IncidentStatus.new,
        severity=Severity.medium,
        confidence=Decimal("0.75"),
        rationale="test",
        correlator_version="1.0.0",
        correlator_rule="test_rule",
    )
    db_session.add(inc)
    return inc


def _make_action(incident_id: uuid.UUID, kind: ActionKind, params: dict) -> Action:
    return Action(
        id=uuid.uuid4(),
        incident_id=incident_id,
        kind=kind,
        classification=ActionClassification.disruptive,
        params=params,
        proposed_by=ActionProposedBy.analyst,
        status=ActionStatus.proposed,
    )


def _make_action_log(action_id: uuid.UUID, reversal_info: dict | None) -> ActionLog:
    return ActionLog(
        action_id=action_id,
        executed_at=datetime.now(timezone.utc),
        executed_by="test",
        result=ActionResult.ok,
        reversal_info=reversal_info,
    )


# ---------------------------------------------------------------------------
# quarantine_host
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quarantine_host_execute_ok(db_session):
    inc = _make_incident(db_session)
    asset = LabAsset(
        id=uuid.uuid4(),
        kind=LabAssetKind.host,
        natural_key="lab-test-01",
        notes="clean",
    )
    db_session.add(asset)
    await db_session.flush()

    action = _make_action(inc.id, ActionKind.quarantine_host_lab, {"host": "lab-test-01"})
    db_session.add(action)
    await db_session.flush()

    result, reason, _ = await quarantine_host.execute(action, db_session)
    assert result == ActionResult.ok
    assert reason is None
    assert "[quarantined:" in (asset.notes or "")


@pytest.mark.asyncio
async def test_quarantine_host_missing_param(db_session):
    inc = _make_incident(db_session)
    await db_session.flush()
    action = _make_action(inc.id, ActionKind.quarantine_host_lab, {})
    db_session.add(action)
    await db_session.flush()

    result, reason, _ = await quarantine_host.execute(action, db_session)
    assert result == ActionResult.fail
    assert "required" in (reason or "")


@pytest.mark.asyncio
async def test_quarantine_host_not_found(db_session):
    inc = _make_incident(db_session)
    await db_session.flush()
    action = _make_action(inc.id, ActionKind.quarantine_host_lab, {"host": "nonexistent"})
    db_session.add(action)
    await db_session.flush()

    result, reason, _ = await quarantine_host.execute(action, db_session)
    assert result == ActionResult.fail
    assert "not found" in (reason or "")


# ---------------------------------------------------------------------------
# kill_process
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kill_process_execute_ok(db_session):
    inc = _make_incident(db_session)
    asset = LabAsset(id=uuid.uuid4(), kind=LabAssetKind.host, natural_key="lab-test-02")
    db_session.add(asset)
    await db_session.flush()

    action = _make_action(
        inc.id,
        ActionKind.kill_process_lab,
        {"host": "lab-test-02", "pid": 4321, "process_name": "malware.exe"},
    )
    db_session.add(action)
    await db_session.flush()

    result, reason, reversal_info = await kill_process.execute(action, db_session)
    assert result == ActionResult.ok
    assert reversal_info is not None
    assert reversal_info["pid"] == 4321
    assert "killed_at" in reversal_info

    # Auto-created evidence request
    from sqlalchemy import select
    er = await db_session.scalar(
        select(EvidenceRequest).where(EvidenceRequest.incident_id == inc.id)
    )
    assert er is not None
    assert er.kind == EvidenceKind.process_list
    assert er.status == EvidenceStatus.open


@pytest.mark.asyncio
async def test_kill_process_missing_pid(db_session):
    inc = _make_incident(db_session)
    asset = LabAsset(id=uuid.uuid4(), kind=LabAssetKind.host, natural_key="lab-test-03")
    db_session.add(asset)
    await db_session.flush()
    action = _make_action(inc.id, ActionKind.kill_process_lab, {"host": "lab-test-03"})
    db_session.add(action)
    await db_session.flush()

    result, reason, _ = await kill_process.execute(action, db_session)
    assert result == ActionResult.fail
    assert "pid" in (reason or "")


# ---------------------------------------------------------------------------
# invalidate_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidate_session_execute_and_revert(db_session):
    inc = _make_incident(db_session)
    user_asset = LabAsset(id=uuid.uuid4(), kind=LabAssetKind.user, natural_key="alice")
    host_asset = LabAsset(id=uuid.uuid4(), kind=LabAssetKind.host, natural_key="lab-test-04")
    now = datetime.now(timezone.utc)
    user_entity = Entity(
        id=uuid.uuid4(), kind=EntityKind.user, natural_key="alice",
        attrs={}, first_seen=now, last_seen=now,
    )
    host_entity = Entity(
        id=uuid.uuid4(), kind=EntityKind.host, natural_key="lab-test-04",
        attrs={}, first_seen=now, last_seen=now,
    )
    db_session.add_all([user_asset, host_asset, user_entity, host_entity])
    await db_session.flush()

    action = _make_action(
        inc.id,
        ActionKind.invalidate_lab_session,
        {"user": "alice", "host": "lab-test-04"},
    )
    action.classification = ActionClassification.reversible
    db_session.add(action)
    await db_session.flush()

    result, reason, reversal_info = await invalidate_session.execute(action, db_session)
    assert result == ActionResult.ok
    assert reversal_info is not None
    session_id = reversal_info["session_id"]

    # Session is now invalidated
    session = await db_session.get(LabSession, uuid.UUID(session_id))
    assert session is not None
    assert session.invalidated_at is not None

    # Revert
    log = _make_action_log(action.id, reversal_info)
    db_session.add(log)
    await db_session.flush()

    revert_result, revert_reason, _ = await invalidate_session.revert(action, log, db_session)
    assert revert_result == ActionResult.ok

    await db_session.refresh(session)
    assert session.invalidated_at is None


# ---------------------------------------------------------------------------
# block_observable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_block_observable_execute_and_revert(db_session):
    inc = _make_incident(db_session)
    await db_session.flush()

    action = _make_action(
        inc.id,
        ActionKind.block_observable,
        {"kind": "ip", "value": "10.0.0.99"},
    )
    action.classification = ActionClassification.reversible
    db_session.add(action)
    await db_session.flush()

    result, reason, reversal_info = await block_observable.execute(action, db_session)
    assert result == ActionResult.ok
    assert reversal_info is not None
    obs_id = reversal_info["blocked_observable_id"]

    from app.db.models import BlockedObservable
    obs = await db_session.get(BlockedObservable, uuid.UUID(obs_id))
    assert obs is not None
    assert obs.active is True
    assert obs.value == "10.0.0.99"
    assert obs.kind == BlockableKind.ip

    # Revert
    log = _make_action_log(action.id, reversal_info)
    db_session.add(log)
    await db_session.flush()

    revert_result, _, _ = await block_observable.revert(action, log, db_session)
    assert revert_result == ActionResult.ok

    await db_session.refresh(obs)
    assert obs.active is False


@pytest.mark.asyncio
async def test_block_observable_invalid_kind(db_session):
    inc = _make_incident(db_session)
    await db_session.flush()
    action = _make_action(inc.id, ActionKind.block_observable, {"kind": "foobar", "value": "x"})
    db_session.add(action)
    await db_session.flush()

    result, reason, _ = await block_observable.execute(action, db_session)
    assert result == ActionResult.fail
    assert "invalid kind" in (reason or "")


# ---------------------------------------------------------------------------
# request_evidence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_evidence_execute_ok(db_session):
    inc = _make_incident(db_session)
    await db_session.flush()

    action = _make_action(
        inc.id,
        ActionKind.request_evidence,
        {"evidence_kind": "process_list"},
    )
    action.classification = ActionClassification.suggest_only
    db_session.add(action)
    await db_session.flush()

    result, reason, reversal_info = await request_evidence.execute(action, db_session)
    assert result == ActionResult.ok
    assert reversal_info is not None
    assert "evidence_request_id" in reversal_info
    assert reversal_info["kind"] == "process_list"

    from sqlalchemy import select
    er = await db_session.scalar(
        select(EvidenceRequest).where(EvidenceRequest.incident_id == inc.id)
    )
    assert er is not None
    assert er.kind == EvidenceKind.process_list
    assert er.status == EvidenceStatus.open
    assert str(er.id) == reversal_info["evidence_request_id"]


@pytest.mark.asyncio
async def test_request_evidence_invalid_kind(db_session):
    inc = _make_incident(db_session)
    await db_session.flush()
    action = _make_action(
        inc.id, ActionKind.request_evidence, {"evidence_kind": "unknown_kind"}
    )
    db_session.add(action)
    await db_session.flush()

    result, reason, _ = await request_evidence.execute(action, db_session)
    assert result == ActionResult.fail
    assert "invalid evidence_kind" in (reason or "")
