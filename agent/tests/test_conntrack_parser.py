"""Tests for cct_agent.parsers.conntrack.

Exercises the format produced by ``conntrack -E -e NEW -o timestamp -o
extended -o id`` (the command line used by ``infra/lab-debian/entrypoint.sh``).
The fixture ``agent/tests/fixtures/conntrack_new.log`` carries one example
of each variant the parser is expected to handle.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cct_agent.parsers.conntrack import (
    ParsedNetworkEvent,
    parse_line,
)

FIXTURE = Path(__file__).parent / "fixtures" / "conntrack_new.log"


def _fixture_lines() -> list[str]:
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def test_tcp_new_parsed_with_original_direction_tuple():
    lines = _fixture_lines()
    parsed = parse_line(lines[0])
    assert isinstance(parsed, ParsedNetworkEvent)
    assert parsed.kind == "network.connection"
    assert parsed.proto == "tcp"
    # Original-direction tuple — NOT the reverse src=172.66.147.243.
    assert parsed.src_ip == "172.18.0.2"
    assert parsed.dst_ip == "172.66.147.243"
    assert parsed.src_port == 55068
    assert parsed.dst_port == 80
    # No id= in this line — fallback path exercised.
    assert parsed.conntrack_id is None


def test_tcp_new_with_conntrack_id_extracted():
    lines = _fixture_lines()
    parsed = parse_line(lines[1])
    assert parsed is not None
    assert parsed.proto == "tcp"
    assert parsed.dst_ip == "203.0.113.42"
    assert parsed.dst_port == 443
    assert parsed.conntrack_id == 12345


def test_udp_new_parsed():
    lines = _fixture_lines()
    parsed = parse_line(lines[2])
    assert parsed is not None
    assert parsed.proto == "udp"
    assert parsed.src_ip == "10.0.0.5"
    assert parsed.dst_ip == "8.8.8.8"
    assert parsed.src_port == 44321
    assert parsed.dst_port == 53


def test_icmp_new_parsed_with_synthesized_ports():
    lines = _fixture_lines()
    parsed = parse_line(lines[3])
    assert parsed is not None
    assert parsed.proto == "icmp"
    assert parsed.src_ip == "10.0.0.5"
    assert parsed.dst_ip == "8.8.8.8"
    # ICMP echo type=8 → dst_port; src_port synthesized to 0.
    assert parsed.src_port == 0
    assert parsed.dst_port == 8


def test_loopback_dropped():
    lines = _fixture_lines()
    # src=127.0.0.1 dst=127.0.0.11 — both inside 127.0.0.0/8.
    assert parse_line(lines[4]) is None


def test_link_local_v4_dropped():
    line = (
        "[1777418600.0]\t[NEW] ipv4 2 udp 17 30 "
        "src=169.254.1.5 dst=169.254.1.10 sport=1000 dport=2000 "
        "[UNREPLIED] src=169.254.1.10 dst=169.254.1.5 sport=2000 dport=1000"
    )
    assert parse_line(line) is None


def test_link_local_v6_dropped():
    line = (
        "[1777418600.0]\t[NEW] ipv6 10 tcp 6 120 SYN_SENT "
        "src=fe80::1 dst=fe80::2 sport=1000 dport=2000 [UNREPLIED] "
        "src=fe80::2 dst=fe80::1 sport=2000 dport=1000"
    )
    assert parse_line(line) is None


def test_ipv6_loopback_dropped():
    line = (
        "[1777418600.0]\t[NEW] ipv6 10 tcp 6 120 SYN_SENT "
        "src=::1 dst=::1 sport=1000 dport=2000 [UNREPLIED] "
        "src=::1 dst=::1 sport=2000 dport=1000"
    )
    assert parse_line(line) is None


def test_malformed_line_returns_none():
    lines = _fixture_lines()
    assert parse_line(lines[5]) is None


def test_empty_line_returns_none():
    assert parse_line("") is None
    assert parse_line("\n") is None


def test_non_new_records_dropped():
    update_line = (
        "[1777418600.0]\t[UPDATE] ipv4 2 tcp 6 120 ESTABLISHED "
        "src=10.0.0.5 dst=8.8.8.8 sport=1000 dport=80 "
        "src=8.8.8.8 dst=10.0.0.5 sport=80 dport=1000 [ASSURED]"
    )
    destroy_line = (
        "[1777418601.0]\t[DESTROY] ipv4 2 tcp 6 src=10.0.0.5 dst=8.8.8.8 "
        "sport=1000 dport=80 src=8.8.8.8 dst=10.0.0.5 sport=80 dport=1000 [ASSURED]"
    )
    assert parse_line(update_line) is None
    assert parse_line(destroy_line) is None


def test_unsupported_proto_dropped():
    igmp_line = (
        "[1777418602.0]\t[NEW] ipv4 2 igmp 2 30 "
        "src=10.0.0.5 dst=224.0.0.1 [UNREPLIED] src=224.0.0.1 dst=10.0.0.5"
    )
    gre_line = (
        "[1777418603.0]\t[NEW] ipv4 2 gre 47 60 "
        "src=10.0.0.5 dst=10.0.0.6 [UNREPLIED] src=10.0.0.6 dst=10.0.0.5"
    )
    assert parse_line(igmp_line) is None
    assert parse_line(gre_line) is None


def test_timestamp_parsed_to_utc():
    lines = _fixture_lines()
    parsed = parse_line(lines[1])
    assert parsed is not None
    expected = datetime.fromtimestamp(1777418400.123456, tz=timezone.utc)
    assert parsed.occurred_at == expected
    assert parsed.occurred_at.tzinfo is timezone.utc


def test_raw_line_preserved():
    lines = _fixture_lines()
    parsed = parse_line(lines[0])
    assert parsed is not None
    assert parsed.raw_line == lines[0]


def test_format_without_address_family_token():
    """Older conntrack-tools (without ``-o extended``) omit ``ipv4 2`` after [NEW]."""
    line = (
        "[1777418700.0]\t[NEW] tcp 6 120 SYN_SENT "
        "src=10.0.0.5 dst=8.8.8.8 sport=1000 dport=443 [UNREPLIED] "
        "src=8.8.8.8 dst=10.0.0.5 sport=443 dport=1000"
    )
    parsed = parse_line(line)
    assert parsed is not None
    assert parsed.proto == "tcp"
    assert parsed.src_ip == "10.0.0.5"
    assert parsed.dst_port == 443


def test_rfc1918_traffic_kept():
    """RFC1918 src+dst is interesting (lateral movement) — must not be filtered."""
    line = (
        "[1777418800.0]\t[NEW] ipv4 2 tcp 6 120 SYN_SENT "
        "src=10.0.0.5 dst=10.0.0.20 sport=1000 dport=445 [UNREPLIED] "
        "src=10.0.0.20 dst=10.0.0.5 sport=445 dport=1000"
    )
    parsed = parse_line(line)
    assert parsed is not None
    assert parsed.src_ip == "10.0.0.5"
    assert parsed.dst_ip == "10.0.0.20"
    assert parsed.dst_port == 445
