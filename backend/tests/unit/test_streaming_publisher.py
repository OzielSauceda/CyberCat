"""Unit tests for the streaming publisher."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.streaming.events import StreamEvent, topic_for, Topic
from app.streaming.publisher import _make_id, publish


def test_make_id_is_sortable_and_unique():
    ids = [_make_id() for _ in range(50)]
    assert len(set(ids)) == 50
    # Sortable: later calls produce lexicographically greater or equal ids (monotone)
    assert ids == sorted(ids)


def test_topic_for_maps_all_event_types():
    mapping = {
        "incident.created": Topic.incidents,
        "incident.updated": Topic.incidents,
        "incident.transitioned": Topic.incidents,
        "detection.fired": Topic.detections,
        "action.proposed": Topic.actions,
        "action.executed": Topic.actions,
        "action.reverted": Topic.actions,
        "evidence.opened": Topic.evidence,
        "evidence.collected": Topic.evidence,
        "evidence.dismissed": Topic.evidence,
        "wazuh.status_changed": Topic.wazuh,
    }
    for event_type, expected_topic in mapping.items():
        assert topic_for(event_type) == expected_topic  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_publish_builds_correct_envelope():
    captured: list[tuple[str, str]] = []

    mock_redis = AsyncMock()

    async def fake_publish(channel: str, payload: str) -> None:
        captured.append((channel, payload))

    mock_redis.publish = fake_publish

    with patch("app.db.redis.get_redis", return_value=mock_redis):
        await publish("incident.created", {"incident_id": "abc", "kind": "identity_compromise", "severity": "high"})

    assert len(captured) == 1
    channel, payload = captured[0]
    assert channel == "cybercat:stream:incidents"

    event = StreamEvent.model_validate_json(payload)
    assert event.type == "incident.created"
    assert event.topic == Topic.incidents
    assert event.data["incident_id"] == "abc"
    # id is non-empty
    assert len(event.id) > 8
    # ts is timezone-aware
    assert event.ts.tzinfo is not None


@pytest.mark.asyncio
async def test_publish_swallows_redis_error():
    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = ConnectionError("redis down")

    with patch("app.db.redis.get_redis", return_value=mock_redis):
        # Must not raise
        await publish("action.proposed", {"action_id": "x", "incident_id": "y", "kind": "tag_incident"})
