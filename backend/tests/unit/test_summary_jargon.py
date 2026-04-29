"""Phase 18.2 — assert plain-language summary fields stay free of jargon.

Covers:
- RecommendedAction.summary: every recommendation produces a non-empty summary
  containing no rule_id substrings, no ATT&CK technique codes (T1234), and no
  raw underscore-laden enum values.

Correlator-rule incident.summary fields are exercised via integration tests.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.db.models import Entity, Incident, IncidentAttack
from app.enums import (
    AttackSource,
    EntityKind,
    IncidentEntityRole,
    IncidentKind,
    IncidentStatus,
    Severity,
)
from app.response.recommendations import recommend_for_incident

_NOW = datetime.now(timezone.utc)
_TECHNIQUE_CODE_RE = re.compile(r"\bT\d{4}\b")


def _incident(kind: IncidentKind = IncidentKind.identity_compromise) -> Incident:
    return Incident(
        id=uuid.uuid4(),
        title="t",
        kind=kind,
        status=IncidentStatus.new,
        severity=Severity.high,
        confidence=Decimal("0.9"),
        rationale="r",
        correlator_version="1",
        correlator_rule="t",
        opened_at=_NOW,
        updated_at=_NOW,
        tags=[],
    )


def _entity(kind: EntityKind, key: str) -> Entity:
    return Entity(
        id=uuid.uuid4(),
        kind=kind,
        natural_key=key,
        attrs={},
        first_seen=_NOW,
        last_seen=_NOW,
    )


def test_recommended_action_summary_is_plain():
    inc = _incident(IncidentKind.identity_endpoint_chain)
    user = _entity(EntityKind.user, "alice")
    host = _entity(EntityKind.host, "lab-debian")
    src_ip = _entity(EntityKind.ip, "203.0.113.7")
    entities = [
        (user, IncidentEntityRole.user),
        (host, IncidentEntityRole.host),
        (src_ip, IncidentEntityRole.source_ip),
    ]
    attack = [
        IncidentAttack(
            incident_id=inc.id,
            tactic="credential-access",
            technique="T1110",
            subtechnique=None,
            source=AttackSource.rule_derived,
        ),
        IncidentAttack(
            incident_id=inc.id,
            tactic="execution",
            technique="T1059",
            subtechnique=None,
            source=AttackSource.rule_derived,
        ),
    ]

    recs = recommend_for_incident(inc, entities, attack, [], max_results=5)

    assert recs, "expected at least one recommendation"
    for rec in recs:
        assert rec.summary, f"summary missing for {rec.kind}"
        # no underscore-laden enum values leaking through
        assert "_" not in rec.summary, f"underscore in summary: {rec.summary!r}"
        # no ATT&CK technique codes leaking through
        assert not _TECHNIQUE_CODE_RE.search(rec.summary), (
            f"technique code in summary: {rec.summary!r}"
        )
        # summary should be shorter or equal length than rationale
        # (rationale carries the technical detail; summary is the lead)
        assert len(rec.summary) <= len(rec.rationale) + 10, (
            f"summary unexpectedly longer than rationale for {rec.kind}: "
            f"summary={rec.summary!r} rationale={rec.rationale!r}"
        )
