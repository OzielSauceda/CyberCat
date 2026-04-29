"""Unit tests for cct_agent.parsers.auditd.AuditdParser."""
from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest

from cct_agent.parsers.auditd import AuditdParser, ParsedProcessEvent

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = "1777374000.000"  # 2026-04-28 ~11:00 UTC (exact value not critical)


def _syscall_line(
    event_id: int,
    *,
    pid: int,
    ppid: int,
    uid: int,
    syscall: int,
    exe: str = '"/bin/bash"',
    exit_val: int = 0,
    ts: str = BASE_TS,
) -> str:
    return (
        f"type=SYSCALL msg=audit({ts}:{event_id}): arch=c000003e "
        f"syscall={syscall} success=yes exit={exit_val} "
        f"a0=55f1000 a1=55f1001 a2=55f1002 a3=0 items=2 "
        f"ppid={ppid} pid={pid} auid={uid} uid={uid} gid={uid} "
        f"euid={uid} suid={uid} fsuid={uid} egid={uid} sgid={uid} fsgid={uid} "
        f"tty=pts0 ses=1 comm=\"bash\" exe={exe} subj=unconfined key=\"cybercat_exec\""
    )


def _execve_line(event_id: int, args: list[str], ts: str = BASE_TS) -> str:
    parts = [f"argc={len(args)}"]
    parts += [f'a{i}="{v}"' for i, v in enumerate(args)]
    return f"type=EXECVE msg=audit({ts}:{event_id}): " + " ".join(parts)


def _path_line(event_id: int, name: str, ts: str = BASE_TS) -> str:
    return (
        f"type=PATH msg=audit({ts}:{event_id}): "
        f'item=0 name="{name}" inode=12345 dev=fd:00 mode=0100755 '
        f"ouid=0 ogid=0 rdev=00:00 nametype=NORMAL"
    )


def _proctitle_line(event_id: int, hex_blob: str, ts: str = BASE_TS) -> str:
    return f"type=PROCTITLE msg=audit({ts}:{event_id}): proctitle={hex_blob}"


def _eoe_line(event_id: int, ts: str = BASE_TS) -> str:
    return f"type=EOE msg=audit({ts}:{event_id}):"


def feed_lines(parser: AuditdParser, lines: list[str]) -> list[ParsedProcessEvent]:
    result = []
    for line in lines:
        result.extend(parser.feed(line))
    return result


# ---------------------------------------------------------------------------
# Test 1: Assembled execve event (happy path with all record types)
# ---------------------------------------------------------------------------


def test_assembled_execve_event():
    parser = AuditdParser()
    lines = [
        _syscall_line(456, pid=5678, ppid=1234, uid=1000, syscall=59, exe='"/bin/bash"'),
        _execve_line(456, ["bash", "-c", "id"]),
        _path_line(456, "/bin/bash"),
        # proctitle: "bash\0-c\0id" = 62617368002D63006964
        _proctitle_line(456, "62617368002D63006964"),
        _eoe_line(456),
    ]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "process.created"
    assert ev.pid == 5678
    assert ev.ppid == 1234
    assert ev.image == "/bin/bash"
    # cmdline comes from EXECVE args (preferred over PROCTITLE)
    assert ev.cmdline == "bash -c id"
    assert ev.audit_event_id == 456
    assert ev.occurred_at.tzinfo is not None
    assert ev.occurred_at.year == 2026
    assert ev.exit_code is None          # process.created has no exit_code
    assert ev.parent_image is None       # resolved downstream by TrackedProcesses
    assert len(ev.raw_lines) == 5


# ---------------------------------------------------------------------------
# Test 2: Missing PROCTITLE — event still parsed from EXECVE args
# ---------------------------------------------------------------------------


def test_missing_proctitle_still_parseable():
    parser = AuditdParser()
    lines = [
        _syscall_line(460, pid=6000, ppid=1234, uid=1000, syscall=59, exe='"/usr/bin/python3"'),
        _execve_line(460, ["/usr/bin/python3", "/tmp/script.py"]),
        _eoe_line(460),
    ]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "process.created"
    assert ev.image == "/usr/bin/python3"
    assert ev.cmdline == "/usr/bin/python3 /tmp/script.py"


# ---------------------------------------------------------------------------
# Test 3: Missing EXECVE and PROCTITLE — cmdline is None, event still valid
# ---------------------------------------------------------------------------


def test_missing_execve_and_proctitle_cmdline_is_none():
    parser = AuditdParser()
    lines = [
        _syscall_line(461, pid=6001, ppid=1234, uid=0, syscall=59, exe='"/bin/sh"'),
        _eoe_line(461),
    ]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "process.created"
    assert ev.image == "/bin/sh"
    assert ev.cmdline is None


# ---------------------------------------------------------------------------
# Test 4: Hex-encoded argv decoded correctly
# ---------------------------------------------------------------------------


def test_hex_argv_decoded_correctly():
    # a0=6C73 → "ls", a1=2D6C61 → "-la", a2=2F657463 → "/etc"
    parser = AuditdParser()
    hex_execve = (
        f"type=EXECVE msg=audit({BASE_TS}:462): argc=3 "
        "a0=6C73 a1=2D6C61 a2=2F657463"
    )
    lines = [
        _syscall_line(462, pid=6002, ppid=1234, uid=0, syscall=59, exe='"/usr/bin/ls"'),
        hex_execve,
        _eoe_line(462),
    ]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.cmdline == "ls -la /etc"


# ---------------------------------------------------------------------------
# Test 5: PROCTITLE fallback when EXECVE is absent
# ---------------------------------------------------------------------------


def test_proctitle_used_when_execve_absent():
    # "bash\0-c\0id" → 62617368002D63006964
    parser = AuditdParser()
    lines = [
        _syscall_line(463, pid=6003, ppid=1234, uid=1000, syscall=59, exe='"/bin/bash"'),
        _proctitle_line(463, "62617368002D63006964"),
        _eoe_line(463),
    ]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.cmdline == "bash -c id"


# ---------------------------------------------------------------------------
# Test 6: PATH item=0 used as image fallback when exe is missing
# ---------------------------------------------------------------------------


def test_path_fallback_for_image():
    # SYSCALL without exe= field
    syscall_no_exe = (
        f"type=SYSCALL msg=audit({BASE_TS}:464): arch=c000003e "
        "syscall=59 success=yes exit=0 a0=55f0 a1=55f1 a2=0 a3=0 "
        "items=2 ppid=1234 pid=6004 auid=0 uid=0 gid=0 euid=0 suid=0 "
        "fsuid=0 egid=0 sgid=0 fsgid=0 tty=pts0 ses=1 comm=\"ls\" "
        'subj=unconfined key="cybercat_exec"'
    )
    lines = [
        syscall_no_exe,
        _execve_line(464, ["ls", "-la"]),
        _path_line(464, "/usr/bin/ls"),
        _eoe_line(464),
    ]
    events = feed_lines(AuditdParser(), lines)

    assert len(events) == 1
    assert events[0].image == "/usr/bin/ls"


# ---------------------------------------------------------------------------
# Test 7: Multi-event interleaving — EOE flushes each event independently
# ---------------------------------------------------------------------------


def test_multi_event_interleaving():
    parser = AuditdParser()
    ts_a, ts_b = "1777374005.000", "1777374006.000"
    # Lines for events 470 and 471 arrive interleaved
    lines = [
        _syscall_line(470, pid=7000, ppid=100, uid=1000, syscall=59, exe='"/bin/bash"', ts=ts_a),
        _syscall_line(471, pid=7001, ppid=100, uid=1000, syscall=59, exe='"/usr/bin/python3"', ts=ts_b),
        _execve_line(470, ["bash", "-i"], ts=ts_a),
        _execve_line(471, ["python3", "exploit.py"], ts=ts_b),
        _path_line(470, "/bin/bash", ts=ts_a),
        _path_line(471, "/usr/bin/python3", ts=ts_b),
        _eoe_line(470, ts=ts_a),   # flushes event 470
        _eoe_line(471, ts=ts_b),   # flushes event 471
    ]
    events = feed_lines(parser, lines)

    assert len(events) == 2
    by_pid = {ev.pid: ev for ev in events}
    assert by_pid[7000].image == "/bin/bash"
    assert by_pid[7000].cmdline == "bash -i"
    assert by_pid[7001].image == "/usr/bin/python3"
    assert by_pid[7001].cmdline == "python3 exploit.py"


# ---------------------------------------------------------------------------
# Test 8: Malformed lines silently skipped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "",
        "garbage line",
        "type=SYSCALL no-msg-header: pid=1",
        "this is not an audit record at all",
        "\x00\x01\x02binary junk",
        "🦊",
        "x" * 5000,
    ],
)
def test_malformed_line_silently_skipped(line: str):
    parser = AuditdParser()
    result = parser.feed(line)
    assert result == []


# ---------------------------------------------------------------------------
# Test 9: Non-execve syscall in otherwise valid event → skipped
# ---------------------------------------------------------------------------


def test_non_execve_syscall_skipped():
    # syscall=2 is 'open', not tracked
    parser = AuditdParser()
    lines = [
        _syscall_line(480, pid=8000, ppid=1234, uid=0, syscall=2),
        _eoe_line(480),
    ]
    events = feed_lines(parser, lines)
    assert events == []


# ---------------------------------------------------------------------------
# Test 10: exit_group (syscall=231) → process.exited
# ---------------------------------------------------------------------------


def test_exit_group_clean_exit():
    parser = AuditdParser()
    syscall_line = (
        f"type=SYSCALL msg=audit({BASE_TS}:500): arch=c000003e "
        "syscall=231 success=yes exit=0 a0=0 a1=0 a2=0 a3=0 "
        "items=0 ppid=1234 pid=5678 auid=1000 uid=1000 gid=1000 "
        "euid=1000 suid=1000 fsuid=1000 egid=1000 sgid=1000 fsgid=1000 "
        'tty=pts0 ses=3 comm="bash" exe="/bin/bash" subj=unconfined '
        'key="cybercat_exit"'
    )
    lines = [syscall_line, _eoe_line(500)]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "process.exited"
    assert ev.pid == 5678
    assert ev.ppid == 1234
    assert ev.exit_code == 0
    assert ev.audit_event_id == 500


def test_exit_group_abnormal_exit():
    parser = AuditdParser()
    syscall_line = (
        f"type=SYSCALL msg=audit({BASE_TS}:501): arch=c000003e "
        "syscall=231 success=yes exit=137 a0=137 a1=0 a2=0 a3=0 "
        "items=0 ppid=1234 pid=5679 auid=1000 uid=1000 gid=1000 "
        "euid=1000 suid=1000 fsuid=1000 egid=1000 sgid=1000 fsgid=1000 "
        'tty=pts0 ses=4 comm="python3" exe="/usr/bin/python3" '
        'subj=unconfined key="cybercat_exit"'
    )
    lines = [syscall_line, _eoe_line(501)]
    events = feed_lines(parser, lines)

    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "process.exited"
    assert ev.pid == 5679
    assert ev.exit_code == 137
    assert ev.image == "/usr/bin/python3"   # image carried from SYSCALL


# ---------------------------------------------------------------------------
# Test 11: flush() drains buffered event with no EOE
# ---------------------------------------------------------------------------


def test_flush_drains_buffered_event():
    parser = AuditdParser()
    # Feed complete event data but no EOE
    lines = [
        _syscall_line(490, pid=9000, ppid=1234, uid=1000, syscall=59, exe='"/bin/sh"'),
        _execve_line(490, ["sh", "-c", "whoami"]),
    ]
    # Nothing emitted yet (no EOE)
    assert feed_lines(parser, lines) == []

    # flush() should return the assembled event
    flushed = parser.flush()
    assert len(flushed) == 1
    ev = flushed[0]
    assert ev.kind == "process.created"
    assert ev.pid == 9000
    assert ev.cmdline == "sh -c whoami"

    # Buffer is drained — second flush returns nothing
    assert parser.flush() == []


# ---------------------------------------------------------------------------
# Test 12: 100-line safety cap flushes without EOE
# ---------------------------------------------------------------------------


def test_buffer_cap_forces_flush():
    parser = AuditdParser()
    # Send 99 CWD lines (valid header, not SYSCALL/EXECVE) then an EOE
    # The 100th line triggers the cap flush
    cwd_line = f"type=CWD msg=audit({BASE_TS}:495): cwd=\"/tmp\""
    syscall = _syscall_line(495, pid=9500, ppid=1234, uid=0, syscall=59, exe='"/bin/ls"')
    lines = [syscall] + [cwd_line] * 99  # 100 lines total (1 SYSCALL + 99 CWD)

    result = []
    for i, line in enumerate(lines):
        evs = parser.feed(line)
        result.extend(evs)
        if evs:
            # Should flush on hitting the cap, not before
            assert i == 99  # zero-indexed: the 100th line triggers

    assert len(result) == 1
    assert result[0].pid == 9500


# ---------------------------------------------------------------------------
# Fixture-driven tests
# ---------------------------------------------------------------------------


def test_execve_fixture_yields_five_process_created_events():
    text = (FIXTURES / "audit_execve.log").read_text(encoding="utf-8")
    parser = AuditdParser()
    events: list[ParsedProcessEvent] = []
    for line in text.splitlines():
        events.extend(parser.feed(line))
    events.extend(parser.flush())

    created = [e for e in events if e.kind == "process.created"]
    assert len(created) == 5

    images = {e.image for e in created}
    assert "/bin/bash" in images
    assert "/usr/bin/python3" in images
    assert "/bin/sh" in images
    assert "/tmp/winword.exe" in images

    # Event 460: exe absent in SYSCALL → image from PATH fallback
    event_460 = next(e for e in created if e.audit_event_id == 460)
    assert event_460.image == "/usr/bin/ls"


def test_execve_fixture_hex_args_decode():
    text = (FIXTURES / "audit_execve.log").read_text(encoding="utf-8")
    parser = AuditdParser()
    events: list[ParsedProcessEvent] = []
    for line in text.splitlines():
        events.extend(parser.feed(line))
    events.extend(parser.flush())

    # Event 458: hex-encoded EXECVE args a0=6C73 a1=2D6C61 a2=2F657463
    event_458 = next(e for e in events if e.audit_event_id == 458)
    assert event_458.cmdline == "ls -la /etc"


def test_exit_fixture_yields_two_process_exited_events():
    text = (FIXTURES / "audit_exit.log").read_text(encoding="utf-8")
    parser = AuditdParser()
    events: list[ParsedProcessEvent] = []
    for line in text.splitlines():
        events.extend(parser.feed(line))
    events.extend(parser.flush())

    exited = [e for e in events if e.kind == "process.exited"]
    assert len(exited) == 2

    by_pid = {e.pid: e for e in exited}
    assert by_pid[5678].exit_code == 0
    assert by_pid[5679].exit_code == 137


def test_all_events_have_utc_timestamps():
    for fixture in ("audit_execve.log", "audit_exit.log"):
        text = (FIXTURES / fixture).read_text(encoding="utf-8")
        parser = AuditdParser()
        events: list[ParsedProcessEvent] = []
        for line in text.splitlines():
            events.extend(parser.feed(line))
        events.extend(parser.flush())
        for ev in events:
            assert ev.occurred_at.tzinfo == timezone.utc, (
                f"{fixture}: event {ev.audit_event_id} has no UTC tzinfo"
            )
