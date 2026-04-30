"""Phase 19 A3.1 — HTTP /events/raw retries once on connection_invalidated.

When Postgres restarts mid-load, in-flight async sessions get a stale
connection that surfaces as `DBAPIError(connection_invalidated=True)` on the
next statement. `with_ingest_retry` must catch that exact case and retry
exactly once with a fresh session before propagating.

This is the HTTP-level twin of `test_postgres_resilience.py` (which exercises
the helper directly). Here we patch the pipeline entry point used by the
router so we can drive the failure deterministically.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from app.ingest.pipeline import IngestResult


def _payload() -> dict:
    return {
        "source": "direct",
        "kind": "auth.failed",
        "occurred_at": datetime.now(UTC).isoformat(),
        "raw": {"src_user": "alice"},
        "normalized": {
            "user": "alice",
            "source_ip": "203.0.113.7",
            "auth_type": "password",
        },
        "dedupe_key": f"retry-test-{uuid4().hex[:12]}",
    }


def _make_invalidated_error() -> DBAPIError:
    err = DBAPIError(statement="INSERT", params={}, orig=Exception("connection lost"))
    err.connection_invalidated = True
    return err


@pytest.mark.asyncio
async def test_http_ingest_retries_on_connection_invalidated(authed_client, truncate_tables):
    """First attempt raises invalidated DBAPIError; second succeeds. Route returns 201."""
    attempts = {"n": 0}
    fake_event_id = uuid4()

    async def fake_pipeline(*_args, **_kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _make_invalidated_error()
        return IngestResult(
            event_id=fake_event_id,
            dedup_hit=False,
            detection_ids=[],
            incident_touched=None,
        )

    with patch(
        "app.api.routers.events.ingest_normalized_event",
        side_effect=fake_pipeline,
    ):
        resp = await authed_client.post("/v1/events/raw", json=_payload())

    assert resp.status_code == 201, f"expected 201 after retry, got {resp.status_code}: {resp.text}"
    assert attempts["n"] == 2, f"expected exactly 2 attempts (1 fail + 1 retry), got {attempts['n']}"
    body = resp.json()
    assert body["event_id"] == str(fake_event_id)


@pytest.mark.asyncio
async def test_http_ingest_propagates_after_two_failures(authed_client, truncate_tables):
    """If both attempts raise invalidated DBAPIError, the retry wrapper gives up after exactly two tries."""
    attempts = {"n": 0}

    async def always_fail(*_args, **_kwargs):
        attempts["n"] += 1
        raise _make_invalidated_error()

    with patch(
        "app.api.routers.events.ingest_normalized_event",
        side_effect=always_fail,
    ):
        with pytest.raises(DBAPIError):
            await authed_client.post("/v1/events/raw", json=_payload())

    assert attempts["n"] == 2, "must give up after exactly one retry"
