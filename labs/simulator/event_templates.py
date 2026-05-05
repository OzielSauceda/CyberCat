"""Parameterized event builders that produce RawEventIn-compatible dicts."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(occurred_at: datetime | None) -> str:
    return (occurred_at or _now()).isoformat()


def auth_failed(
    user: str,
    source_ip: str,
    auth_type: str = "ssh",
    occurred_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> dict:
    normalized = {"user": user, "source_ip": source_ip, "auth_type": auth_type}
    return {
        "source": "seeder",
        "kind": "auth.failed",
        "occurred_at": _ts(occurred_at),
        "raw": normalized.copy(),
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }


def auth_succeeded(
    user: str,
    source_ip: str,
    auth_type: str = "ssh",
    occurred_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> dict:
    normalized = {"user": user, "source_ip": source_ip, "auth_type": auth_type}
    return {
        "source": "seeder",
        "kind": "auth.succeeded",
        "occurred_at": _ts(occurred_at),
        "raw": normalized.copy(),
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }


def session_started(
    user: str,
    host: str,
    session_id: str | None = None,
    occurred_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> dict:
    sid = session_id or f"sim-{uuid.uuid4().hex[:8]}"
    normalized = {"user": user, "host": host, "session_id": sid}
    return {
        "source": "seeder",
        "kind": "session.started",
        "occurred_at": _ts(occurred_at),
        "raw": normalized.copy(),
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }


def process_created(
    host: str,
    image: str,
    cmdline: str,
    pid: int = 4242,
    ppid: int = 2828,
    user: str | None = None,
    parent_image: str | None = None,
    occurred_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> dict:
    normalized: dict = {
        "host": host,
        "pid": pid,
        "ppid": ppid,
        "image": image,
        "cmdline": cmdline,
    }
    if user:
        normalized["user"] = user
    if parent_image:
        normalized["parent_image"] = parent_image
    return {
        "source": "seeder",
        "kind": "process.created",
        "occurred_at": _ts(occurred_at),
        "raw": normalized.copy(),
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }


def file_created(
    host: str,
    path: str,
    user: str | None = None,
    occurred_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> dict:
    normalized: dict = {"host": host, "path": path}
    if user:
        normalized["user"] = user
    return {
        "source": "seeder",
        "kind": "file.created",
        "occurred_at": _ts(occurred_at),
        "raw": normalized.copy(),
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }


def network_connection(
    host: str,
    src_ip: str,
    dst_ip: str,
    dst_port: int,
    proto: str = "tcp",
    occurred_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> dict:
    normalized = {
        "host": host,
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "dst_port": dst_port,
        "proto": proto,
    }
    return {
        "source": "seeder",
        "kind": "network.connection",
        "occurred_at": _ts(occurred_at),
        "raw": normalized.copy(),
        "normalized": normalized,
        "dedupe_key": dedupe_key,
    }
