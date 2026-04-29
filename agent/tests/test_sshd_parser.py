"""Unit tests for cct_agent.parsers.sshd.parse_line."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cct_agent.events import build_event
from cct_agent.parsers.sshd import ParsedEvent, parse_line

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Individual line patterns
# ---------------------------------------------------------------------------


def test_failed_password_invalid_user_bsd():
    line = "Apr 28 11:00:01 lab-debian sshd[1234]: Failed password for invalid user baduser from 203.0.113.42 port 49852 ssh2"
    pe = parse_line(line, year_hint=2026)
    assert pe is not None
    assert pe.kind == "auth.failed"
    assert pe.user == "baduser"
    assert pe.source_ip == "203.0.113.42"
    assert pe.auth_type == "password"
    assert pe.sshd_pid == 1234
    assert pe.occurred_at == datetime(2026, 4, 28, 11, 0, 1, tzinfo=timezone.utc)


def test_failed_password_known_user_bsd():
    line = "Apr 28 11:00:30 lab-debian sshd[1240]: Failed password for realuser from 203.0.113.42 port 50001 ssh2"
    pe = parse_line(line, year_hint=2026)
    assert pe is not None
    assert pe.kind == "auth.failed"
    assert pe.user == "realuser"


def test_accepted_password_bsd():
    line = "Apr 28 11:01:00 lab-debian sshd[1245]: Accepted password for realuser from 10.0.0.50 port 50100 ssh2"
    pe = parse_line(line, year_hint=2026)
    assert pe is not None
    assert pe.kind == "auth.succeeded"
    assert pe.user == "realuser"
    assert pe.source_ip == "10.0.0.50"
    assert pe.auth_type == "password"


def test_accepted_publickey_with_trailing_fingerprint():
    line = "Apr 28 11:01:05 lab-debian sshd[1250]: Accepted publickey for realuser from 10.0.0.50 port 50105 ssh2: RSA SHA256:abcdef1234567890"
    pe = parse_line(line, year_hint=2026)
    assert pe is not None
    assert pe.kind == "auth.succeeded"
    assert pe.auth_type == "publickey"


def test_session_opened_bsd_no_uid():
    line = "Apr 28 11:01:00 lab-debian sshd[1245]: pam_unix(sshd:session): session opened for user realuser by (uid=0)"
    pe = parse_line(line, year_hint=2026)
    assert pe is not None
    assert pe.kind == "session.started"
    assert pe.user == "realuser"
    assert pe.session_uid is None
    assert pe.sshd_pid == 1245


def test_session_opened_ubuntu_with_uid():
    line = "2026-04-28T11:00:30Z ubuntu-host sshd[2003]: pam_unix(sshd:session): session opened for user alice(uid=1001) by (uid=0)"
    pe = parse_line(line)
    assert pe is not None
    assert pe.kind == "session.started"
    assert pe.user == "alice"
    assert pe.session_uid == 1001


def test_session_closed_bsd():
    line = "Apr 28 11:05:00 lab-debian sshd[1245]: pam_unix(sshd:session): session closed for user realuser"
    pe = parse_line(line, year_hint=2026)
    assert pe is not None
    assert pe.kind == "session.ended"
    assert pe.user == "realuser"


def test_iso_timestamp_with_microseconds():
    line = "2026-04-28T11:00:01.123456+00:00 ubuntu-host sshd[2001]: Failed password for invalid user attacker from 198.51.100.7 port 60001 ssh2"
    pe = parse_line(line)
    assert pe is not None
    assert pe.occurred_at.year == 2026
    assert pe.occurred_at.month == 4
    assert pe.occurred_at.tzinfo is not None
    # Microseconds preserved
    assert pe.occurred_at.microsecond == 123456


def test_iso_timestamp_z_suffix():
    line = "2026-04-28T11:00:30Z ubuntu-host sshd[2003]: Accepted password for alice from 198.51.100.7 port 60010 ssh2"
    pe = parse_line(line)
    assert pe is not None
    assert pe.occurred_at == datetime(2026, 4, 28, 11, 0, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Negative paths — non-sshd / unparseable lines must return None, not raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "",
        "garbage line",
        "Apr 28 11:05:02 lab-debian CRON[1300]: pam_unix(cron:session): session opened for user root by (uid=0)",
        "Apr 28 11:05:01 lab-debian sshd[9999]: Connection from 10.0.0.50 port 50105 on 172.20.0.5 port 22",
        "2026-04-28T11:05:01Z ubuntu-host systemd-logind[123]: New session 42 of user alice.",
        # Malformed timestamp
        "NOTAMONTH 28 11:00:01 lab-debian sshd[1234]: Failed password for x from 1.2.3.4 port 1 ssh2",
    ],
)
def test_unparseable_returns_none(line: str):
    assert parse_line(line, year_hint=2026) is None


def test_does_not_raise_on_random_input():
    for line in ["\x00\x01\x02", "🦊", "x" * 5000]:
        # Must never raise, only return None
        assert parse_line(line) is None


# ---------------------------------------------------------------------------
# Fixture-driven end-to-end (parse → build_event)
# ---------------------------------------------------------------------------


def test_debian_fixture_yields_expected_event_kinds():
    text = (FIXTURES / "auth_debian.log").read_text(encoding="utf-8")
    parsed = [parse_line(line, year_hint=2026) for line in text.splitlines()]
    parsed = [p for p in parsed if p is not None]
    kinds = [p.kind for p in parsed]
    # 5 auth.failed (4 baduser + 1 realuser), 2 auth.succeeded (pwd + pk),
    # 2 session.started, 1 session.ended. The CRON line and the bare Connection
    # line do not parse.
    assert kinds.count("auth.failed") == 5
    assert kinds.count("auth.succeeded") == 2
    assert kinds.count("session.started") == 2
    assert kinds.count("session.ended") == 1


def test_ubuntu_fixture_yields_expected_event_kinds():
    text = (FIXTURES / "auth_ubuntu.log").read_text(encoding="utf-8")
    parsed = [parse_line(line) for line in text.splitlines()]
    parsed = [p for p in parsed if p is not None]
    kinds = [p.kind for p in parsed]
    # 2 auth.failed, 1 auth.succeeded, 1 session.started, 1 session.ended.
    # The systemd-logind line does not parse.
    assert kinds.count("auth.failed") == 2
    assert kinds.count("auth.succeeded") == 1
    assert kinds.count("session.started") == 1
    assert kinds.count("session.ended") == 1


# ---------------------------------------------------------------------------
# build_event integration
# ---------------------------------------------------------------------------


def _parse(line: str) -> ParsedEvent:
    pe = parse_line(line, year_hint=2026)
    assert pe is not None, f"line did not parse: {line!r}"
    return pe


def test_build_event_auth_failed_shape():
    pe = _parse(
        "Apr 28 11:00:01 lab-debian sshd[1234]: "
        "Failed password for invalid user baduser from 203.0.113.42 port 49852 ssh2"
    )
    ev = build_event(pe, host="lab-debian")
    assert ev["source"] == "direct"
    assert ev["kind"] == "auth.failed"
    assert ev["normalized"] == {
        "user": "baduser",
        "source_ip": "203.0.113.42",
        "auth_type": "password",
    }
    assert ev["raw"]["host"] == "lab-debian"
    assert ev["raw"]["sshd_pid"] == 1234
    assert isinstance(ev["dedupe_key"], str) and ev["dedupe_key"].startswith(
        "direct:auth.failed:"
    )


def test_build_event_session_uses_pid_based_session_id():
    open_pe = _parse(
        "Apr 28 11:01:00 lab-debian sshd[1245]: "
        "pam_unix(sshd:session): session opened for user realuser by (uid=0)"
    )
    close_pe = _parse(
        "Apr 28 11:05:00 lab-debian sshd[1245]: "
        "pam_unix(sshd:session): session closed for user realuser"
    )
    open_ev = build_event(open_pe, host="lab-debian")
    close_ev = build_event(close_pe, host="lab-debian")
    # Both session events for the same connection (same sshd PID)
    # produce the same session_id, which matches them across started/ended.
    assert open_ev["normalized"]["session_id"] == close_ev["normalized"]["session_id"]
    assert open_ev["normalized"]["session_id"] == "sshd-lab-debian-1245"


def test_build_event_dedupe_key_is_stable():
    line = (
        "Apr 28 11:00:01 lab-debian sshd[1234]: "
        "Failed password for invalid user baduser from 203.0.113.42 port 49852 ssh2"
    )
    a = build_event(_parse(line), host="lab-debian")
    b = build_event(_parse(line), host="lab-debian")
    assert a["dedupe_key"] == b["dedupe_key"]


def test_build_event_normalized_contains_exactly_required_keys():
    """Backend normalizer rejects extra unknown keys? It does not — but locking
    the normalized shape to the canonical spec keeps drift visible."""
    cases = {
        "auth.failed": {"user", "source_ip", "auth_type"},
        "auth.succeeded": {"user", "source_ip", "auth_type"},
        "session.started": {"user", "host", "session_id"},
        "session.ended": {"user", "host", "session_id"},
    }
    samples = {
        "auth.failed": "Apr 28 11:00:01 lab-debian sshd[1234]: Failed password for x from 1.2.3.4 port 1 ssh2",
        "auth.succeeded": "Apr 28 11:00:01 lab-debian sshd[1234]: Accepted password for x from 1.2.3.4 port 1 ssh2",
        "session.started": "Apr 28 11:00:01 lab-debian sshd[1234]: pam_unix(sshd:session): session opened for user x by (uid=0)",
        "session.ended": "Apr 28 11:00:01 lab-debian sshd[1234]: pam_unix(sshd:session): session closed for user x",
    }
    for kind, expected_keys in cases.items():
        ev = build_event(_parse(samples[kind]), host="lab-debian")
        assert set(ev["normalized"].keys()) == expected_keys, (
            kind,
            ev["normalized"],
        )
