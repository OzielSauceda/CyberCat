"""Phase 19 — detection-as-code regression suite.

Drives `labs/fixtures/manifest.yaml`: for every fixture entry it replays the
JSONL events into the test backend (using the in-process httpx client) and
asserts the resulting detections match `must_fire` / `must_not_fire`.

This test is the gate that prevents detector behavior from regressing as the
codebase evolves. Adding a new detector requires adding both:
  - a positive fixture (proves it fires), and
  - at least one benign fixture in must_not_fire (proves no false positive).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from app.db.models import (
    Action,
    BlockedObservable,
    Detection,
    Incident,
    IncidentEvent,
)
from app.db.session import AsyncSessionLocal
from app.enums import (
    ActionClassification,
    ActionKind,
    ActionProposedBy,
    ActionStatus,
    BlockableKind,
    IncidentKind,
    IncidentStatus,
    Severity,
)

def _find_fixtures_dir() -> Path | None:
    """Resolve labs/fixtures whether the tests run from the repo (backend/...)
    or from inside the backend container where /app/labs/fixtures is bind-mirrored."""
    test_file = Path(__file__).resolve()
    candidates = [
        # In-repo: backend/tests/integration/test_X.py → repo/labs/fixtures
        test_file.parents[3] / "labs" / "fixtures",
        # Container: /app/tests/integration/test_X.py → /app/labs/fixtures
        Path("/app/labs/fixtures"),
    ]
    for c in candidates:
        if (c / "manifest.yaml").exists():
            return c
    return None


_FIXTURES_DIR = _find_fixtures_dir()
_MANIFEST_PATH = _FIXTURES_DIR / "manifest.yaml" if _FIXTURES_DIR else None

# All Python detectors in the system. Manifest must reference each in `must_fire`
# at least once; otherwise we'd be quietly missing positive coverage.
_KNOWN_RULES = {
    "py.auth.failed_burst",
    "py.auth.anomalous_source_success",
    "py.process.suspicious_child",
    "py.blocked_observable_match",
}


def _load_manifest() -> list[dict]:
    if _MANIFEST_PATH is None or not _MANIFEST_PATH.exists():
        return []
    return yaml.safe_load(_MANIFEST_PATH.read_text(encoding="utf-8"))


_MANIFEST = _load_manifest()
_HAVE_FIXTURES = bool(_MANIFEST)
pytestmark = pytest.mark.skipif(
    not _HAVE_FIXTURES,
    reason=f"detection-as-code manifest not found (looked under labs/fixtures/)",
)


def _materialize_event(template: dict, base_time: datetime) -> dict:
    event = dict(template)
    offset = event.pop("_t_offset_sec", 0)
    event["occurred_at"] = (base_time - timedelta(seconds=int(offset))).isoformat()
    return event


async def _seed_setup(setup: dict) -> None:
    """Apply `setup:` directives from a manifest entry before replay."""
    if not setup:
        return
    blocks = setup.get("block_observable", [])
    if not blocks:
        return

    async with AsyncSessionLocal() as db:
        # block_observable rows require a non-null blocked_by_action_id (FK);
        # synthesize an Action row to anchor them.
        anchor_incident = Incident(
            id=uuid.uuid4(),
            title="fixture seed: blocked observables",
            kind=IncidentKind.unknown,
            status=IncidentStatus.new,
            severity=Severity.info,
            confidence=__import__("decimal").Decimal("0.10"),
            rationale="Synthetic incident for fixture-time blocked-observable seeding.",
            summary="Synthetic.",
            tags=[],
            correlator_version="fixture-seed",
            correlator_rule="fixture-seed",
            dedupe_key=f"fixture-seed:{uuid.uuid4()}",
        )
        db.add(anchor_incident)
        await db.flush()

        anchor_action = Action(
            id=uuid.uuid4(),
            incident_id=anchor_incident.id,
            kind=ActionKind.block_observable,
            classification=ActionClassification.reversible,
            params={},
            proposed_by=ActionProposedBy.system,
            status=ActionStatus.executed,
        )
        db.add(anchor_action)
        await db.flush()

        for entry in blocks:
            db.add(BlockedObservable(
                id=uuid.uuid4(),
                kind=BlockableKind(entry["kind"]),
                value=entry["value"],
                blocked_by_action_id=anchor_action.id,
                active=True,
            ))
        await db.commit()


async def _detected_rules_after(base_time: datetime) -> set[str]:
    """Return the set of rule_ids that produced a detection at or after base_time
    minus a small slack window."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Detection.rule_id).where(
                Detection.created_at >= base_time - timedelta(seconds=5)
            )
        )
        return {r[0] for r in rows.all()}


# ---------------------------------------------------------------------------
# Manifest-shape sanity check (runs once per session, no replay)
# ---------------------------------------------------------------------------

class TestManifestShape:
    def test_every_known_detector_has_at_least_one_positive_fixture(self):
        positive = set()
        for entry in _MANIFEST:
            for rule in entry.get("must_fire", []):
                positive.add(rule)
        missing = _KNOWN_RULES - positive
        assert not missing, (
            f"detectors with no positive fixture in manifest: {sorted(missing)}"
            " — every detector must have a `must_fire` entry"
        )

    def test_no_unknown_rule_ids_referenced(self):
        referenced: set[str] = set()
        for entry in _MANIFEST:
            referenced.update(entry.get("must_fire", []))
            referenced.update(entry.get("must_not_fire", []))
        unknown = referenced - _KNOWN_RULES
        assert not unknown, (
            f"manifest references unknown detector rule_ids: {sorted(unknown)}"
            f" — known set is {sorted(_KNOWN_RULES)}"
        )


# ---------------------------------------------------------------------------
# Per-fixture parametrized regression
# ---------------------------------------------------------------------------

@pytest.fixture(params=_MANIFEST or [{"fixture": "no-manifest", "must_fire": [], "must_not_fire": []}],
                ids=lambda e: e.get("fixture", "no-manifest"))
def manifest_entry(request):
    return request.param


class TestDetectionFixtures:
    async def test_fixture_replays_to_expected_rule_set(
        self, manifest_entry, authed_client, truncate_tables
    ):
        fixture_path = _FIXTURES_DIR / manifest_entry["fixture"]
        assert fixture_path.exists(), f"fixture file missing: {fixture_path}"

        await _seed_setup(manifest_entry.get("setup") or {})

        # Mark the time window so we only inspect detections produced by THIS replay.
        cutoff = datetime.now(timezone.utc)

        # POST every event in the fixture
        for line_no, line in enumerate(
            fixture_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            template = json.loads(line)
            payload = _materialize_event(template, base_time=cutoff)
            resp = await authed_client.post("/v1/events/raw", json=payload)
            assert resp.status_code in (200, 201), (
                f"{fixture_path.name}:{line_no} rejected: "
                f"{resp.status_code} {resp.text[:200]}"
            )

        fired = await _detected_rules_after(cutoff)

        must_fire = set(manifest_entry.get("must_fire", []))
        must_not_fire = set(manifest_entry.get("must_not_fire", []))

        missing = must_fire - fired
        assert not missing, (
            f"{fixture_path.name}: expected to fire {sorted(must_fire)}, "
            f"missing {sorted(missing)} (actual: {sorted(fired)})"
        )

        unexpected = must_not_fire & fired
        assert not unexpected, (
            f"{fixture_path.name}: rule(s) fired but should not have: "
            f"{sorted(unexpected)} (actual: {sorted(fired)})"
        )
