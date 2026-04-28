"""Unit tests for the RecommendedActions engine (Phase 15.1).

Pure unit tests — no DB, no async, no HTTP.  All objects are instantiated
directly without a session since we only read attributes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.models import Action, Entity, Incident, IncidentAttack
from app.enums import (
    ActionClassification,
    ActionKind,
    ActionProposedBy,
    ActionStatus,
    AttackSource,
    EntityKind,
    IncidentEntityRole,
    IncidentKind,
    IncidentStatus,
    Severity,
)
from app.response.recommendations import recommend_for_incident


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _incident(kind: IncidentKind = IncidentKind.identity_compromise) -> Incident:
    return Incident(
        id=uuid.uuid4(),
        title="Test incident",
        kind=kind,
        status=IncidentStatus.new,
        severity=Severity.high,
        confidence=Decimal("0.9"),
        rationale="test",
        correlator_version="1",
        correlator_rule="test_rule",
        opened_at=_NOW,
        updated_at=_NOW,
        tags=[],
    )


def _entity(kind: EntityKind, natural_key: str, attrs: dict | None = None) -> Entity:
    return Entity(
        id=uuid.uuid4(),
        kind=kind,
        natural_key=natural_key,
        attrs=attrs or {},
        first_seen=_NOW,
        last_seen=_NOW,
    )


def _attack(technique: str, tactic: str = "credential-access") -> IncidentAttack:
    return IncidentAttack(
        id=1,
        incident_id=uuid.uuid4(),
        tactic=tactic,
        technique=technique,
        subtechnique=None,
        source=AttackSource.rule_derived,
    )


def _action(
    kind: ActionKind,
    params: dict,
    status: ActionStatus = ActionStatus.executed,
) -> Action:
    return Action(
        id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        kind=kind,
        classification=ActionClassification.reversible,
        params=params,
        proposed_by=ActionProposedBy.analyst,
        status=status,
        proposed_at=_NOW,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_entities_returns_empty():
    inc = _incident(IncidentKind.identity_compromise)
    recs = recommend_for_incident(inc, [], [], [])
    assert recs == []


def test_unknown_kind_no_host_returns_empty():
    inc = _incident(IncidentKind.unknown)
    recs = recommend_for_incident(inc, [], [], [])
    assert recs == []


def test_unknown_kind_with_host_returns_request_evidence():
    inc = _incident(IncidentKind.unknown)
    host = _entity(EntityKind.host, "lab-host-1")
    entities = [(host, IncidentEntityRole.host)]
    recs = recommend_for_incident(inc, entities, [], [])
    assert len(recs) == 1
    assert recs[0].kind == ActionKind.request_evidence
    assert recs[0].params["target_host"] == "lab-host-1"


def test_identity_compromise_with_user_and_source_ip():
    inc = _incident(IncidentKind.identity_compromise)
    user = _entity(EntityKind.user, "alice")
    ip = _entity(EntityKind.ip, "203.0.113.42")
    entities = [
        (user, IncidentEntityRole.user),
        (ip, IncidentEntityRole.source_ip),
    ]
    recs = recommend_for_incident(inc, entities, [], [])
    kinds = [r.kind for r in recs]
    # Top rec should be block_observable (highest base score for identity_compromise)
    assert recs[0].kind == ActionKind.block_observable
    assert recs[0].params == {"kind": "ip", "value": "203.0.113.42"}
    # No host → no invalidate_lab_session (requires user + host) and no quarantine
    assert ActionKind.quarantine_host_lab not in kinds
    assert ActionKind.invalidate_lab_session not in kinds


def test_endpoint_compromise_with_host_only():
    inc = _incident(IncidentKind.endpoint_compromise)
    host = _entity(EntityKind.host, "lab-host-1")
    entities = [(host, IncidentEntityRole.host)]
    recs = recommend_for_incident(inc, entities, [], [])
    kinds = [r.kind for r in recs]
    assert ActionKind.quarantine_host_lab in kinds
    assert ActionKind.request_evidence in kinds
    # No IP → no block_observable
    assert ActionKind.block_observable not in kinds
    # No user → no invalidate_lab_session
    assert ActionKind.invalidate_lab_session not in kinds


def test_identity_endpoint_chain_with_all_entities_and_techniques():
    inc = _incident(IncidentKind.identity_endpoint_chain)
    user = _entity(EntityKind.user, "alice")
    host = _entity(EntityKind.host, "lab-host-1")
    ip = _entity(EntityKind.ip, "203.0.113.42")
    entities = [
        (user, IncidentEntityRole.user),
        (host, IncidentEntityRole.host),
        (ip, IncidentEntityRole.source_ip),
    ]
    attack = [
        _attack("T1110"),  # Brute Force → boosts block_observable
        _attack("T1078"),  # Valid Accounts → boosts invalidate_lab_session
        _attack("T1059"),  # Command & Scripting → boosts quarantine_host_lab
    ]
    recs = recommend_for_incident(inc, entities, attack, [])
    assert len(recs) == 4
    kinds = [r.kind for r in recs]
    # block_observable should be #1 (base 50 + T1110 boost 20 = 70)
    assert recs[0].kind == ActionKind.block_observable
    # quarantine (40+10=50) and invalidate (30+20=50) both boosted above flag_host (20)
    top_kinds = set(kinds[:3])
    assert ActionKind.block_observable in top_kinds
    assert ActionKind.quarantine_host_lab in top_kinds
    assert ActionKind.invalidate_lab_session in top_kinds
    # request_evidence (score=10) is 5th — cut off by max_results=4; flag_host_in_lab (20) is last
    assert ActionKind.request_evidence not in kinds
    assert recs[-1].kind == ActionKind.flag_host_in_lab


def test_already_executed_block_observable_excluded():
    inc = _incident(IncidentKind.identity_compromise)
    ip = _entity(EntityKind.ip, "1.2.3.4")
    entities = [(ip, IncidentEntityRole.source_ip)]
    executed = _action(
        ActionKind.block_observable,
        {"kind": "ip", "value": "1.2.3.4"},
        status=ActionStatus.executed,
    )
    recs = recommend_for_incident(inc, entities, [], [executed])
    kinds = [r.kind for r in recs]
    assert ActionKind.block_observable not in kinds


def test_reverted_block_observable_is_re_recommended():
    inc = _incident(IncidentKind.identity_compromise)
    ip = _entity(EntityKind.ip, "1.2.3.4")
    entities = [(ip, IncidentEntityRole.source_ip)]
    reverted = _action(
        ActionKind.block_observable,
        {"kind": "ip", "value": "1.2.3.4"},
        status=ActionStatus.reverted,
    )
    recs = recommend_for_incident(inc, entities, [], [reverted])
    kinds = [r.kind for r in recs]
    assert ActionKind.block_observable in kinds


def test_subtechnique_inherits_boost():
    inc = _incident(IncidentKind.identity_compromise)
    ip = _entity(EntityKind.ip, "203.0.113.42")
    entities = [(ip, IncidentEntityRole.source_ip)]
    attack = [_attack("T1110.003")]  # Subtechnique — should still match T1110 prefix
    recs_boosted = recommend_for_incident(inc, entities, attack, [])
    recs_plain = recommend_for_incident(inc, entities, [], [])
    # With T1110.003 boost, block_observable score should be higher
    boosted_score_rank = next(i for i, r in enumerate(recs_boosted) if r.kind == ActionKind.block_observable)
    plain_score_rank = next(i for i, r in enumerate(recs_plain) if r.kind == ActionKind.block_observable)
    assert boosted_score_rank <= plain_score_rank  # boosted ranks at least as high


def test_excluded_kinds_never_appear():
    inc = _incident(IncidentKind.identity_endpoint_chain)
    user = _entity(EntityKind.user, "alice")
    host = _entity(EntityKind.host, "lab-host-1")
    ip = _entity(EntityKind.ip, "203.0.113.42")
    entities = [
        (user, IncidentEntityRole.user),
        (host, IncidentEntityRole.host),
        (ip, IncidentEntityRole.source_ip),
    ]
    recs = recommend_for_incident(inc, entities, [], [])
    kinds = [r.kind for r in recs]
    assert ActionKind.tag_incident not in kinds
    assert ActionKind.elevate_severity not in kinds
    assert ActionKind.kill_process_lab not in kinds


def test_priority_field_is_1_indexed_rank():
    inc = _incident(IncidentKind.endpoint_compromise)
    host = _entity(EntityKind.host, "lab-host-1")
    ip = _entity(EntityKind.ip, "203.0.113.42")
    entities = [
        (host, IncidentEntityRole.host),
        (ip, IncidentEntityRole.source_ip),
    ]
    recs = recommend_for_incident(inc, entities, [], [])
    for i, rec in enumerate(recs, start=1):
        assert rec.priority == i


def test_classification_fields_populated():
    inc = _incident(IncidentKind.endpoint_compromise)
    host = _entity(EntityKind.host, "lab-host-1")
    entities = [(host, IncidentEntityRole.host)]
    recs = recommend_for_incident(inc, entities, [], [])
    for rec in recs:
        assert rec.classification in ActionClassification
        assert rec.classification_reason
        assert rec.rationale
        assert rec.target_summary


def test_max_results_respected():
    inc = _incident(IncidentKind.identity_endpoint_chain)
    user = _entity(EntityKind.user, "alice")
    host = _entity(EntityKind.host, "lab-host-1")
    ip = _entity(EntityKind.ip, "203.0.113.42")
    entities = [
        (user, IncidentEntityRole.user),
        (host, IncidentEntityRole.host),
        (ip, IncidentEntityRole.source_ip),
    ]
    recs = recommend_for_incident(inc, entities, [], [], max_results=2)
    assert len(recs) <= 2
