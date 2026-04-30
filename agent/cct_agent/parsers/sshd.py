"""sshd /var/log/auth.log line parser.

Recognizes four patterns relevant to v1 (see docs/phase-16-plan.md):

  - "Failed password for [invalid user ]<user> from <ip> port <port> ssh2"
       → auth.failed
  - "Accepted (password|publickey) for <user> from <ip> port <port> ssh2[: ...]"
       → auth.succeeded
  - "pam_unix(sshd:session): session opened for user <user>[(uid=<uid>)] by ..."
       → session.started
  - "pam_unix(sshd:session): session closed for user <user>"
       → session.ended

Anything else returns ``None``. Unparseable lines are the caller's
responsibility to log/skip — the parser never raises on input.

Both syslog timestamp formats are supported:
  - BSD legacy: "Apr 28 10:00:00"          (Debian 12 default rsyslog)
  - ISO 8601:   "2026-04-28T10:00:00+00:00" (Ubuntu 22.04+ default rsyslog)

BSD timestamps don't carry a year; ``year_hint`` (defaulting to current UTC
year) supplies one. This is correct as long as the log is being tailed live;
historical logs spanning a year boundary should pass an explicit ``year_hint``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ParsedEvent:
    """Structured result of parsing a single sshd auth.log line.

    Fields not relevant for a given kind are ``None``:
      - ``source_ip`` and ``auth_type`` are set on auth.* events only.
      - ``session_uid`` is set on session.started when the pam_unix line
        carried "(uid=NNN)"; otherwise None.
    """

    kind: str
    occurred_at: datetime
    user: str
    sshd_pid: int
    source_ip: str | None
    auth_type: str | None
    session_uid: int | None
    raw_line: str


# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------

_SYSLOG_PREFIX = re.compile(
    r"""^
    (?:
        (?P<bsd_ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})
      | (?P<iso_ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))
    )
    \s+
    (?P<host>\S+)
    \s+
    sshd\[(?P<pid>\d+)\]:\s+
    (?P<msg>.*)$
    """,
    re.VERBOSE,
)

_FAILED = re.compile(
    r"^Failed password for (?:invalid user )?(?P<user>\S+) from (?P<ip>\S+) port \d+ ssh2$"
)

_ACCEPTED = re.compile(
    r"^Accepted (?P<auth_type>password|publickey) for (?P<user>\S+) "
    r"from (?P<ip>\S+) port \d+ ssh2"
)

_SESSION_OPEN = re.compile(
    r"^pam_unix\(sshd:session\): session opened for user "
    r"(?P<user>[A-Za-z_][A-Za-z0-9_-]*)"
    r"(?:\(uid=(?P<uid>\d+)\))?"
    r"(?:\s+by\s+\(uid=\d+\))?$"
)

_SESSION_CLOSE = re.compile(
    r"^pam_unix\(sshd:session\): session closed for user "
    r"(?P<user>[A-Za-z_][A-Za-z0-9_-]*)$"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_line(line: str, year_hint: int | None = None) -> ParsedEvent | None:
    """Parse a single auth.log line. Return None for non-v1 / unparseable lines."""
    line = line.rstrip("\r\n")
    if not line:
        return None

    prefix = _SYSLOG_PREFIX.match(line)
    if prefix is None:
        return None

    occurred_at = _parse_ts(prefix.group("bsd_ts"), prefix.group("iso_ts"), year_hint)
    if occurred_at is None:
        return None

    pid = int(prefix.group("pid"))
    msg = prefix.group("msg")

    if (m := _FAILED.match(msg)) is not None:
        return ParsedEvent(
            kind="auth.failed",
            occurred_at=occurred_at,
            user=m.group("user"),
            sshd_pid=pid,
            source_ip=m.group("ip"),
            auth_type="password",
            session_uid=None,
            raw_line=line,
        )

    if (m := _ACCEPTED.match(msg)) is not None:
        return ParsedEvent(
            kind="auth.succeeded",
            occurred_at=occurred_at,
            user=m.group("user"),
            sshd_pid=pid,
            source_ip=m.group("ip"),
            auth_type=m.group("auth_type"),
            session_uid=None,
            raw_line=line,
        )

    if (m := _SESSION_OPEN.match(msg)) is not None:
        uid_str = m.group("uid")
        return ParsedEvent(
            kind="session.started",
            occurred_at=occurred_at,
            user=m.group("user"),
            sshd_pid=pid,
            source_ip=None,
            auth_type=None,
            session_uid=int(uid_str) if uid_str else None,
            raw_line=line,
        )

    if (m := _SESSION_CLOSE.match(msg)) is not None:
        return ParsedEvent(
            kind="session.ended",
            occurred_at=occurred_at,
            user=m.group("user"),
            sshd_pid=pid,
            source_ip=None,
            auth_type=None,
            session_uid=None,
            raw_line=line,
        )

    return None


def _parse_ts(
    bsd_ts: str | None, iso_ts: str | None, year_hint: int | None
) -> datetime | None:
    """Return a tz-aware UTC datetime, or None if the timestamp is unparseable."""
    if iso_ts is not None:
        s = iso_ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    if bsd_ts is not None:
        year = year_hint if year_hint is not None else datetime.now(UTC).year
        try:
            # "Apr  3 ..." (single-digit day) has two spaces; strptime handles both.
            dt = datetime.strptime(f"{year} {bsd_ts}", "%Y %b %d %H:%M:%S")
        except ValueError:
            return None
        return dt.replace(tzinfo=UTC)

    return None
