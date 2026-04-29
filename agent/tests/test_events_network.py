"""Unit tests for cct_agent.events building network.connection events.

Verifies the dict shape against the backend ``RawEventIn`` schema and the
required-field registry in ``backend/app/ingest/normalizer.py`` (validated
at runtime so a backend schema change here is loud, not silent).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from cct_agent.events import build_event
from cct_agent.parsers.conntrack import ParsedNetworkEvent

# Make backend imports available so we can validate against the live schemas.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.schemas.events import RawEventIn   # noqa: E402
from app.ingest.normalizer import validate_normalized   # noqa: E402

HOST = "lab-debian"
TS = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


def _net(
    *,
    src_ip: str = "10.0.0.5",
    dst_ip: str = "203.0.113.42",
    src_port: int = 54321,
    dst_port: int = 443,
    proto: str = "tcp",
    conntrack_id: int | None = 12345,
    raw_line: str = "[1.0]\t[NEW] tcp 6 120 SYN_SENT src=10.0.0.5 dst=203.0.113.42 sport=54321 dport=443",
) -> ParsedNetworkEvent:
    return ParsedNetworkEvent(
        kind="network.connection",
        occurred_at=TS,
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        proto=proto,
        conntrack_id=conntrack_id,
        raw_line=raw_line,
    )


def test_network_event_dict_matches_raw_event_in():
    parsed = _net()
    event = build_event(parsed, host=HOST)

    # Pydantic validation = source-of-truth for RawEventIn shape.
    RawEventIn(**event)

    assert event["source"] == "direct"
    assert event["kind"] == "network.connection"
    assert event["normalized"] == {
        "host": HOST,
        "src_ip": "10.0.0.5",
        "dst_ip": "203.0.113.42",
        "dst_port": 443,
        "proto": "tcp",
    }
    assert validate_normalized("network.connection", event["normalized"]) == []


def test_network_event_required_fields_present():
    parsed = _net()
    event = build_event(parsed, host=HOST)
    n = event["normalized"]
    # Backend's required-field set for network.connection.
    for field in ("host", "src_ip", "dst_ip", "dst_port", "proto"):
        assert field in n, f"required field {field} missing from normalized"


def test_network_event_dedupe_key_uses_conntrack_id_when_present():
    parsed = _net(conntrack_id=12345)
    event = build_event(parsed, host=HOST)
    assert event["dedupe_key"] == (
        "direct:network.connection:12345:10.0.0.5:203.0.113.42:443"
    )


def test_network_event_dedupe_key_falls_back_to_hash_without_id():
    raw = (
        "[1.0]\t[NEW] tcp 6 120 SYN_SENT "
        "src=10.0.0.5 dst=203.0.113.42 sport=54321 dport=443"
    )
    parsed = _net(conntrack_id=None, raw_line=raw)
    event = build_event(parsed, host=HOST)
    # SHA256 prefix path — 16-char hex suffix, stable across calls.
    prefix = "direct:network.connection:"
    assert event["dedupe_key"].startswith(prefix)
    suffix = event["dedupe_key"][len(prefix) :]
    assert len(suffix) == 16
    assert all(c in "0123456789abcdef" for c in suffix)
    again = build_event(parsed, host=HOST)
    assert event["dedupe_key"] == again["dedupe_key"]


def test_network_event_dedupe_key_distinct_per_dst_port():
    e1 = build_event(_net(dst_port=80, conntrack_id=999), host=HOST)
    e2 = build_event(_net(dst_port=443, conntrack_id=999), host=HOST)
    assert e1["dedupe_key"] != e2["dedupe_key"]


def test_network_event_carries_src_port_and_conntrack_id_in_raw():
    parsed = _net()
    event = build_event(parsed, host=HOST)
    assert event["raw"]["src_port"] == 54321
    assert event["raw"]["conntrack_id"] == 12345
    assert event["raw"]["raw_line"] == parsed.raw_line


def test_network_event_udp_proto_passes_validation():
    parsed = _net(proto="udp", dst_port=53)
    event = build_event(parsed, host=HOST)
    RawEventIn(**event)
    assert event["normalized"]["proto"] == "udp"
    assert validate_normalized("network.connection", event["normalized"]) == []


def test_network_event_icmp_with_synthesized_ports():
    parsed = _net(proto="icmp", src_port=0, dst_port=8, conntrack_id=None)
    event = build_event(parsed, host=HOST)
    RawEventIn(**event)
    assert event["normalized"]["proto"] == "icmp"
    assert event["normalized"]["dst_port"] == 8


def test_network_event_occurred_at_iso_format():
    parsed = _net()
    event = build_event(parsed, host=HOST)
    assert event["occurred_at"] == TS.isoformat()


def test_network_event_dispatch_via_isinstance():
    """build_event() must dispatch ParsedNetworkEvent to _network_event,
    not fall through to the sshd ``parsed.kind`` branches."""
    parsed = _net()
    event = build_event(parsed, host=HOST)
    assert event["kind"] == "network.connection"
    assert event["source"] == "direct"
