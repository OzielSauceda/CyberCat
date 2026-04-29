"""Unit tests for cct_agent.process_state.TrackedProcesses."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cct_agent.parsers.auditd import ParsedProcessEvent
from cct_agent.process_state import TrackedProcesses


def _created(
    pid: int,
    *,
    ppid: int | None = 1234,
    image: str | None = "/bin/bash",
    user: str | None = "alice",
    cmdline: str | None = "bash -i",
    parent_image: str | None = None,
    audit_event_id: int = 0,
) -> ParsedProcessEvent:
    return ParsedProcessEvent(
        kind="process.created",
        occurred_at=datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc),
        pid=pid,
        ppid=ppid,
        user=user,
        image=image,
        cmdline=cmdline,
        parent_image=parent_image,
        exit_code=None,
        audit_event_id=audit_event_id,
        raw_lines=[],
    )


def _exited(
    pid: int,
    *,
    ppid: int | None = 1234,
    image: str | None = None,
    user: str | None = None,
    exit_code: int | None = 0,
    audit_event_id: int = 0,
) -> ParsedProcessEvent:
    return ParsedProcessEvent(
        kind="process.exited",
        occurred_at=datetime(2026, 4, 28, 12, 5, 0, tzinfo=timezone.utc),
        pid=pid,
        ppid=ppid,
        user=user,
        image=image,
        cmdline=None,
        parent_image=None,
        exit_code=exit_code,
        audit_event_id=audit_event_id,
        raw_lines=[],
    )


def test_record_with_unknown_parent_leaves_parent_image_none():
    cache = TrackedProcesses()
    ev = cache.record(_created(pid=100, ppid=1234, image="/bin/bash"))
    assert ev.parent_image is None
    assert len(cache) == 1


def test_record_resolves_parent_image_from_prior_record():
    cache = TrackedProcesses()
    # parent first
    cache.record(_created(pid=200, ppid=1, image="/usr/bin/winword.exe"))
    # then child
    child = cache.record(_created(pid=201, ppid=200, image="/bin/cmd.exe"))
    assert child.parent_image == "/usr/bin/winword.exe"


def test_record_does_not_overwrite_existing_parent_image():
    cache = TrackedProcesses()
    cache.record(_created(pid=300, ppid=1, image="/bin/parent"))
    child = cache.record(
        _created(pid=301, ppid=300, image="/bin/child", parent_image="/explicit/path")
    )
    assert child.parent_image == "/explicit/path"


def test_record_evicts_oldest_when_cap_exceeded():
    cache = TrackedProcesses(max_size=3)
    cache.record(_created(pid=1))
    cache.record(_created(pid=2))
    cache.record(_created(pid=3))
    cache.record(_created(pid=4))  # evicts pid=1

    assert len(cache) == 3
    # pid 1 evicted → its exit cannot be matched
    assert cache.resolve_exit(_exited(pid=1)) is None
    # pid 2 still tracked
    assert cache.resolve_exit(_exited(pid=2)) is not None


def test_record_lru_touches_parent_on_lookup():
    cache = TrackedProcesses(max_size=3)
    cache.record(_created(pid=10, ppid=1, image="/bin/parent"))     # oldest
    cache.record(_created(pid=11))
    cache.record(_created(pid=12))
    # spawn child of pid=10 → bumps pid=10 to most-recent
    cache.record(_created(pid=13, ppid=10))
    # That insertion would have evicted the oldest (pid=10 if it weren't touched).
    # cap=3, so after 4 insertions one gets evicted; pid=11 should be the victim.
    assert cache.resolve_exit(_exited(pid=10)) is not None
    assert cache.resolve_exit(_exited(pid=11)) is None  # evicted


def test_resolve_exit_returns_none_on_miss():
    cache = TrackedProcesses()
    assert cache.resolve_exit(_exited(pid=9999)) is None


def test_resolve_exit_pops_on_hit():
    cache = TrackedProcesses()
    cache.record(_created(pid=400, image="/bin/sh", user="bob"))
    first = cache.resolve_exit(_exited(pid=400))
    assert first is not None
    assert len(cache) == 0
    # Second resolve is a miss
    assert cache.resolve_exit(_exited(pid=400)) is None


def test_resolve_exit_enriches_missing_fields():
    cache = TrackedProcesses()
    cache.record(_created(pid=500, image="/usr/bin/python3", user="charlie"))
    exit_ev = cache.resolve_exit(_exited(pid=500, image=None, user=None))
    assert exit_ev is not None
    assert exit_ev.image == "/usr/bin/python3"
    assert exit_ev.user == "charlie"


def test_resolve_exit_does_not_override_present_fields():
    cache = TrackedProcesses()
    cache.record(_created(pid=600, image="/cached/image", user="cached_user"))
    exit_ev = cache.resolve_exit(
        _exited(pid=600, image="/exit/image", user="exit_user")
    )
    assert exit_ev is not None
    assert exit_ev.image == "/exit/image"
    assert exit_ev.user == "exit_user"


def test_record_rejects_wrong_kind():
    cache = TrackedProcesses()
    with pytest.raises(ValueError):
        cache.record(_exited(pid=1))


def test_resolve_exit_rejects_wrong_kind():
    cache = TrackedProcesses()
    with pytest.raises(ValueError):
        cache.resolve_exit(_created(pid=1))


def test_record_with_null_ppid_does_not_crash():
    cache = TrackedProcesses()
    ev = cache.record(_created(pid=700, ppid=None))
    assert ev.parent_image is None
    assert len(cache) == 1


def test_repeat_pid_overwrites_record():
    """An audit event with a pid that's still in the cache (e.g. PID reuse
    across kernel namespaces or after a missed exit) overwrites cleanly."""
    cache = TrackedProcesses()
    cache.record(_created(pid=800, image="/bin/old"))
    cache.record(_created(pid=800, image="/bin/new"))
    assert len(cache) == 1
    exit_ev = cache.resolve_exit(_exited(pid=800))
    assert exit_ev is not None
    assert exit_ev.image == "/bin/new"
