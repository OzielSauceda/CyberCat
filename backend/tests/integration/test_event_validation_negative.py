"""Phase 19 — POST /v1/events/raw rejects malformed payloads at the API boundary.

The new RawEventIn validators bound:
- raw           ≤ 64 KB serialized
- normalized    ≤ 16 KB serialized
- occurred_at   in [now-30d, now+5m]
- dedupe_key    matches ^[A-Za-z0-9_:.-]{1,128}$

A valid payload at the size + time boundaries still succeeds.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _valid_payload(**overrides) -> dict:
    base = {
        "source": "direct",
        "kind": "auth.failed",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "raw": {"src_user": "alice"},
        "normalized": {
            "user": "alice",
            "source_ip": "203.0.113.7",
            "auth_type": "password",
        },
        "dedupe_key": "test-alice-1234",
    }
    base.update(overrides)
    return base


def _validation_error_msg(resp_json: dict) -> str:
    """Return concatenated error messages from a pydantic 422 body for assertions."""
    detail = resp_json.get("detail")
    if isinstance(detail, list):
        return " | ".join(d.get("msg", "") for d in detail)
    return str(detail or resp_json)


# ---------------------------------------------------------------------------
# Size validation
# ---------------------------------------------------------------------------

class TestPayloadSizeLimits:
    async def test_oversize_raw_rejected(self, authed_client, truncate_tables):
        # 70 KB > 64 KB cap
        oversize_blob = "x" * (70 * 1024)
        payload = _valid_payload(raw={"giant": oversize_blob})
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422
        msg = _validation_error_msg(resp.json())
        assert "raw" in msg.lower() and "exceeds" in msg.lower()

    async def test_oversize_normalized_rejected(self, authed_client, truncate_tables):
        oversize_blob = "y" * (20 * 1024)  # 20 KB > 16 KB cap
        payload = _valid_payload(
            normalized={
                "user": "alice", "source_ip": "203.0.113.7",
                "auth_type": "password",
                "padding": oversize_blob,
            }
        )
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422
        msg = _validation_error_msg(resp.json())
        assert "normalized" in msg.lower() and "exceeds" in msg.lower()

    async def test_payload_at_boundary_accepted(self, authed_client, truncate_tables):
        # ~60 KB raw — well under 64 KB. Must accept.
        payload = _valid_payload(raw={"src_user": "alice", "extra": "z" * (60 * 1024)})
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 201, f"unexpected: {resp.status_code} {resp.text[:200]}"


# ---------------------------------------------------------------------------
# Timestamp range validation
# ---------------------------------------------------------------------------

class TestTimestampRange:
    async def test_far_past_rejected(self, authed_client, truncate_tables):
        far_past = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        payload = _valid_payload(occurred_at=far_past)
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422
        msg = _validation_error_msg(resp.json())
        assert "occurred_at" in msg or "past" in msg.lower()

    async def test_far_future_rejected(self, authed_client, truncate_tables):
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        payload = _valid_payload(occurred_at=far_future)
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422
        msg = _validation_error_msg(resp.json())
        assert "occurred_at" in msg or "future" in msg.lower()

    async def test_24h_old_accepted(self, authed_client, truncate_tables):
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        payload = _valid_payload(occurred_at=old, dedupe_key="ts-old-test-1")
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 201

    async def test_within_clock_skew_future_accepted(self, authed_client, truncate_tables):
        # 2 minutes in the future is within the 5-minute tolerance
        near_future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        payload = _valid_payload(
            occurred_at=near_future, dedupe_key="ts-skew-test-1"
        )
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# dedupe_key format
# ---------------------------------------------------------------------------

class TestDedupeKeyFormat:
    async def test_whitespace_rejected(self, authed_client, truncate_tables):
        payload = _valid_payload(dedupe_key="has whitespace")
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422
        msg = _validation_error_msg(resp.json())
        assert "dedupe_key" in msg

    async def test_too_long_rejected(self, authed_client, truncate_tables):
        payload = _valid_payload(dedupe_key="a" * 129)
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422

    async def test_control_char_rejected(self, authed_client, truncate_tables):
        # NUL byte is rejected (not in printable ASCII range)
        payload = _valid_payload(dedupe_key="bad\x00key")
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 422

    async def test_valid_dedupe_key_accepted(self, authed_client, truncate_tables):
        payload = _valid_payload(dedupe_key="agent:host_lab.deb-1234")
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 201

    async def test_no_dedupe_key_accepted(self, authed_client, truncate_tables):
        payload = _valid_payload()
        del payload["dedupe_key"]
        resp = await authed_client.post("/v1/events/raw", json=payload)
        assert resp.status_code == 201
