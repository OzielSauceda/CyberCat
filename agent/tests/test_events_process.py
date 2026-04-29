"""Unit tests for cct_agent.events building process.* events.

Verifies the dict shape against the backend ``RawEventIn`` schema and the
required-field registry in ``backend/app/ingest/normalizer.py`` (validated
at runtime so a backend schema change here is loud, not silent).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cct_agent.events import build_event
from cct_agent.parsers.auditd import ParsedProcessEvent

# Make backend imports available so we can validate against the live schemas.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.schemas.events import RawEventIn   # noqa: E402
from app.ingest.normalizer import validate_normalized   # noqa: E402

HOST = "lab-debian"
TS = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


def _created(
    *,
    pid: int = 5678,
    ppid: int | None = 1234,
    image: str | None = "/bin/bash",
    cmdline: str | None = "bash -c id",
    user: str | None = "alice",
    parent_image: str | None = None,
    audit_event_id: int = 9001,
) -> ParsedProcessEvent:
    return ParsedProcessEvent(
        kind="process.created",
        occurred_at=TS,
        pid=pid,
        ppid=ppid,
        user=user,
        image=image,
        cmdline=cmdline,
        parent_image=parent_image,
        exit_code=None,
        audit_event_id=audit_event_id,
        raw_lines=["type=SYSCALL ...", "type=EXECVE ..."],
    )


def _exited(
    *,
    pid: int = 5678,
    user: str | None = "alice",
    image: str | None = "/bin/bash",
    exit_code: int | None = 0,
    audit_event_id: int = 9002,
) -> ParsedProcessEvent:
    return ParsedProcessEvent(
        kind="process.exited",
        occurred_at=TS,
        pid=pid,
        ppid=1234,
        user=user,
        image=image,
        cmdline=None,
        parent_image=None,
        exit_code=exit_code,
        audit_event_id=audit_event_id,
        raw_lines=["type=SYSCALL ..."],
    )


def test_process_created_dict_matches_raw_event_in():
    parsed = _created(parent_image="/usr/bin/winword.exe")
    event = build_event(parsed, host=HOST)

    # Pydantic validation = source-of-truth for RawEventIn shape
    RawEventIn(**event)

    assert event["source"] == "direct"
    assert event["kind"] == "process.created"
    assert event["normalized"] == {
        "host": HOST,
        "pid": 5678,
        "ppid": 1234,
        "image": "/bin/bash",
        "cmdline": "bash -c id",
        "user": "alice",
        "parent_image": "/usr/bin/winword.exe",
    }
    assert event["dedupe_key"] == "direct:process.created:9001:5678"
    assert validate_normalized("process.created", event["normalized"]) == []


def test_process_created_omits_optional_fields_when_absent():
    parsed = _created(user=None, parent_image=None)
    event = build_event(parsed, host=HOST)
    n = event["normalized"]
    assert "user" not in n
    assert "parent_image" not in n
    assert validate_normalized("process.created", n) == []


def test_process_created_missing_required_field_raises():
    parsed = _created(image=None)
    with pytest.raises(ValueError, match="missing required"):
        build_event(parsed, host=HOST)


def test_process_exited_dict_matches_raw_event_in():
    parsed = _exited(exit_code=0)
    event = build_event(parsed, host=HOST)

    RawEventIn(**event)

    assert event["kind"] == "process.exited"
    assert event["normalized"] == {
        "host": HOST,
        "pid": 5678,
        "user": "alice",
        "image": "/bin/bash",
    }
    assert event["raw"]["exit_code"] == 0
    assert event["dedupe_key"] == "direct:process.exited:9002:5678"
    assert validate_normalized("process.exited", event["normalized"]) == []


def test_process_exited_minimum_required_only():
    parsed = _exited(user=None, image=None, exit_code=None)
    event = build_event(parsed, host=HOST)
    n = event["normalized"]
    assert n == {"host": HOST, "pid": 5678}
    assert "exit_code" not in event["raw"]
    assert validate_normalized("process.exited", n) == []


def test_process_created_dedupe_key_stable_across_calls():
    parsed = _created()
    a = build_event(parsed, host=HOST)
    b = build_event(parsed, host=HOST)
    assert a["dedupe_key"] == b["dedupe_key"]


def test_process_created_dedupe_key_distinct_per_pid():
    e1 = build_event(_created(pid=100, audit_event_id=1), host=HOST)
    e2 = build_event(_created(pid=200, audit_event_id=1), host=HOST)
    assert e1["dedupe_key"] != e2["dedupe_key"]


def test_raw_carries_audit_event_id_and_lines():
    parsed = _created()
    event = build_event(parsed, host=HOST)
    assert event["raw"]["audit_event_id"] == 9001
    assert event["raw"]["raw_lines"] == ["type=SYSCALL ...", "type=EXECVE ..."]
