"""Integration tests for the Wazuh poller — indexer is stubbed via httpx_mock."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingest.wazuh_decoder import decode_wazuh_alert
from app.ingest.wazuh_poller import build_query

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wazuh"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ── build_query tests (pure, no I/O) ─────────────────────────────────────────

def test_first_run_query_uses_range_no_search_after():
    q = build_query(None, 100, 5)
    filters = q["query"]["bool"]["filter"]
    has_range = any("range" in f for f in filters)
    assert has_range
    assert "search_after" not in q


def test_cursor_query_uses_search_after_not_range():
    cursor = ["2026-04-21T10:00:00.000Z", "AX12345"]
    q = build_query(cursor, 100, 5)
    filters = q["query"]["bool"]["filter"]
    has_range = any("range" in f for f in filters)
    assert not has_range
    assert q["search_after"] == cursor


def test_batch_size_honoured():
    q = build_query(None, 50, 5)
    assert q["size"] == 50


def test_sort_order_is_asc_timestamp_then_id():
    q = build_query(None, 100, 5)
    assert q["sort"] == [{"@timestamp": "asc"}, {"_id": "asc"}]


# ── decoder drop-doesn't-wedge ────────────────────────────────────────────────

def test_none_result_from_decoder_does_not_raise():
    alert = _load("sshd-failed.json")
    alert["rule"]["groups"] = []  # force drop
    result = decode_wazuh_alert(alert)
    assert result is None  # poller would increment dropped and continue


# ── dedup key stability ───────────────────────────────────────────────────────

def test_dedupe_key_is_underscore_id():
    alert = _load("sshd-failed.json")
    result = decode_wazuh_alert(alert)
    assert result is not None
    assert result.dedupe_key == alert["_id"]
