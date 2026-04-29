"""Event builders for the cct-agent.

Derived from ``labs/simulator/event_templates.py`` (Phase 6+) but with
``source="direct"`` and dedupe_keys generated from a stable hash of the raw
log line (sshd, conntrack) or the audit event id (auditd), so restart-replay
is idempotent.

Three parser families feed this module:
  - ``ParsedEvent``         (sshd)      → auth.* and session.*
  - ``ParsedProcessEvent``  (auditd)    → process.created / process.exited
  - ``ParsedNetworkEvent``  (conntrack) → network.connection

``build_event()`` dispatches on dataclass type.

Required fields per kind (locked by the backend ``_REQUIRED`` table):

    auth.failed        : {user, source_ip, auth_type}
    auth.succeeded     : {user, source_ip, auth_type}
    session.started    : {user, host, session_id}
    session.ended      : {user, host, session_id}
    process.created    : {host, pid, ppid, image, cmdline}
    process.exited     : {host, pid}
    network.connection : {host, src_ip, dst_ip, dst_port, proto}

If any of these change in the backend, the agent's tests will fail loudly —
``backend/app/ingest/normalizer.py`` is the single source of truth.
"""
from __future__ import annotations

import hashlib
from typing import Any

from cct_agent.parsers.auditd import ParsedProcessEvent
from cct_agent.parsers.conntrack import ParsedNetworkEvent
from cct_agent.parsers.sshd import ParsedEvent


def build_event(
    parsed: ParsedEvent | ParsedProcessEvent | ParsedNetworkEvent,
    host: str,
) -> dict[str, Any]:
    """Map a ParsedEvent / ParsedProcessEvent / ParsedNetworkEvent → backend ``RawEventIn`` payload."""
    if isinstance(parsed, ParsedProcessEvent):
        return _process_event(parsed, host)
    if isinstance(parsed, ParsedNetworkEvent):
        return _network_event(parsed, host)
    if parsed.kind == "auth.failed":
        return _auth_event(parsed, host, kind="auth.failed")
    if parsed.kind == "auth.succeeded":
        return _auth_event(parsed, host, kind="auth.succeeded")
    if parsed.kind == "session.started":
        return _session_event(parsed, host, kind="session.started")
    if parsed.kind == "session.ended":
        return _session_event(parsed, host, kind="session.ended")
    raise ValueError(f"Unknown ParsedEvent.kind: {parsed.kind!r}")


def _auth_event(parsed: ParsedEvent, host: str, *, kind: str) -> dict[str, Any]:
    if parsed.source_ip is None or parsed.auth_type is None:
        # Defensive: parser should never produce auth.* events without these fields.
        raise ValueError(f"auth event missing source_ip/auth_type: {parsed!r}")
    normalized = {
        "user": parsed.user,
        "source_ip": parsed.source_ip,
        "auth_type": parsed.auth_type,
    }
    raw = {
        "host": host,
        "sshd_pid": parsed.sshd_pid,
        "raw_line": parsed.raw_line,
    }
    return {
        "source": "direct",
        "kind": kind,
        "occurred_at": parsed.occurred_at.isoformat(),
        "raw": raw,
        "normalized": normalized,
        "dedupe_key": _dedupe_key(parsed),
    }


def _session_event(parsed: ParsedEvent, host: str, *, kind: str) -> dict[str, Any]:
    # sshd forks per connection; the auth handler and the session handler
    # share the same PID for one connection, so PID + host gives a stable
    # session id that matches between session.started and session.ended.
    session_id = f"sshd-{host}-{parsed.sshd_pid}"
    normalized = {
        "user": parsed.user,
        "host": host,
        "session_id": session_id,
    }
    raw: dict[str, Any] = {
        "host": host,
        "sshd_pid": parsed.sshd_pid,
        "raw_line": parsed.raw_line,
    }
    if parsed.session_uid is not None:
        raw["uid"] = parsed.session_uid
    return {
        "source": "direct",
        "kind": kind,
        "occurred_at": parsed.occurred_at.isoformat(),
        "raw": raw,
        "normalized": normalized,
        "dedupe_key": _dedupe_key(parsed),
    }


def _dedupe_key(parsed: ParsedEvent) -> str:
    """Deterministic key derived from the raw line.

    Two lines that are byte-identical produce the same key; the backend's
    ``find_duplicate`` short-circuits on `(source="direct", dedupe_key)`,
    so re-tailing the same line on agent restart is idempotent.
    """
    h = hashlib.sha256(parsed.raw_line.encode("utf-8")).hexdigest()[:16]
    return f"direct:{parsed.kind}:{h}"


def _process_event(parsed: ParsedProcessEvent, host: str) -> dict[str, Any]:
    """Map a ParsedProcessEvent → backend ``RawEventIn`` payload.

    process.created requires {host, pid, ppid, image, cmdline}; we send
    everything we know plus optional ``user`` and ``parent_image``.

    process.exited requires {host, pid}; ``image``, ``user``, and
    ``exit_code`` ride along when available so the analyst UI can show
    them without an extra DB lookup.
    """
    if parsed.kind == "process.created":
        if parsed.ppid is None or parsed.image is None or parsed.cmdline is None:
            # Backend will reject — drop loudly rather than ship and have it 422.
            raise ValueError(
                f"process.created missing required fields: {parsed!r}"
            )
        normalized: dict[str, Any] = {
            "host": host,
            "pid": parsed.pid,
            "ppid": parsed.ppid,
            "image": parsed.image,
            "cmdline": parsed.cmdline,
        }
        if parsed.user is not None:
            normalized["user"] = parsed.user
        if parsed.parent_image is not None:
            normalized["parent_image"] = parsed.parent_image
    elif parsed.kind == "process.exited":
        normalized = {
            "host": host,
            "pid": parsed.pid,
        }
        if parsed.user is not None:
            normalized["user"] = parsed.user
        if parsed.image is not None:
            normalized["image"] = parsed.image
    else:  # pragma: no cover — Literal narrowing
        raise ValueError(f"Unsupported ParsedProcessEvent.kind: {parsed.kind!r}")

    raw: dict[str, Any] = {
        "host": host,
        "audit_event_id": parsed.audit_event_id,
        "raw_lines": parsed.raw_lines,
    }
    if parsed.exit_code is not None:
        raw["exit_code"] = parsed.exit_code

    return {
        "source": "direct",
        "kind": parsed.kind,
        "occurred_at": parsed.occurred_at.isoformat(),
        "raw": raw,
        "normalized": normalized,
        "dedupe_key": (
            f"direct:{parsed.kind}:{parsed.audit_event_id}:{parsed.pid}"
        ),
    }


def _network_event(parsed: ParsedNetworkEvent, host: str) -> dict[str, Any]:
    """Map a ParsedNetworkEvent → backend ``RawEventIn`` payload.

    network.connection requires {host, src_ip, dst_ip, dst_port, proto}; we
    send everything we know plus ``src_port`` and the original conntrack
    line in ``raw``.

    Dedupe key prefers the conntrack ``id=`` field when present (monotonic
    per-kernel-boot, so restart-replay is idempotent). Falls back to a
    SHA256 of the raw line when ``id=`` is absent — same robustness pattern
    as the sshd parser.
    """
    normalized: dict[str, Any] = {
        "host": host,
        "src_ip": parsed.src_ip,
        "dst_ip": parsed.dst_ip,
        "dst_port": parsed.dst_port,
        "proto": parsed.proto,
    }
    raw: dict[str, Any] = {
        "host": host,
        "src_port": parsed.src_port,
        "conntrack_id": parsed.conntrack_id,
        "raw_line": parsed.raw_line,
    }

    if parsed.conntrack_id is not None:
        dedupe_key = (
            f"direct:network.connection:{parsed.conntrack_id}:"
            f"{parsed.src_ip}:{parsed.dst_ip}:{parsed.dst_port}"
        )
    else:
        h = hashlib.sha256(parsed.raw_line.encode("utf-8")).hexdigest()[:16]
        dedupe_key = f"direct:network.connection:{h}"

    return {
        "source": "direct",
        "kind": "network.connection",
        "occurred_at": parsed.occurred_at.isoformat(),
        "raw": raw,
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }
