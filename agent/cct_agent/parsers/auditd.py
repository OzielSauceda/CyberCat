"""auditd /var/log/audit/audit.log line parser.

Recognises two kernel audit record sequences (x86-64 Linux):

  execve chain  (syscall 59)  → process.created
  exit_group    (syscall 231) → process.exited

Records belonging to one kernel event share an event-id embedded in the
``msg=audit(TIMESTAMP:EVENT_ID):`` header.  The parser buffers lines by
event-id and flushes when ``type=EOE`` (End Of Event) is received, or when
the per-event buffer hits the 100-line safety cap.  ``flush()`` drains any
remaining buffers at EOF.

This model handles both sequential and interleaved delivery:
auditd guarantees EOE at the end of each event, so we flush on that rather
than on a simple "id changed" heuristic — the two strategies are equivalent
for sequential records but the EOE approach also handles true interleaving.

Hex-encoded arguments (auditd's fallback for args containing special
characters) are decoded via ``bytes.fromhex``, with ``errors='replace'``
for non-UTF-8 content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class ParsedProcessEvent:
    """Structured result of parsing one auditd execve / exit_group event group.

    Fields not relevant for a given kind are ``None``:
      - ``ppid``, ``image``, ``cmdline`` are populated for process.created.
      - ``exit_code`` is populated for process.exited.
      - ``parent_image`` is always ``None`` here; resolved by TrackedProcesses
        in the next pipeline stage.
    """

    kind: Literal["process.created", "process.exited"]
    occurred_at: datetime
    pid: int
    ppid: int | None
    user: str | None
    image: str | None
    cmdline: str | None
    parent_image: str | None
    exit_code: int | None
    audit_event_id: int
    raw_lines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------

# Shared header: type, timestamp float, event_id, body
_HEADER = re.compile(
    r"^type=(\S+)\s+msg=audit\((\d+\.\d+):(\d+)\):\s*(.*)$"
)

# SYSCALL body fields
_SC_PID     = re.compile(r"\bpid=(\d+)")
_SC_PPID    = re.compile(r"\bppid=(\d+)")
_SC_UID     = re.compile(r"\buid=(\d+)")
_SC_SYSCALL = re.compile(r"\bsyscall=(\d+)")
_SC_EXIT    = re.compile(r"\bexit=(-?\d+)")
_SC_EXE     = re.compile(r'\bexe="([^"]*)"')

# EXECVE body: argument count and individual args (quoted or bare hex)
_EXECVE_ARGC = re.compile(r"\bargc=(\d+)")
_EXECVE_ARG  = re.compile(r'\ba(\d+)=(?:"([^"]*)"|([\da-fA-F]{2,}))')

# PATH body: item=0 name="..."
_PATH_ITEM0  = re.compile(r'\bitem=0\b.*?\bname="([^"]*)"')

# PROCTITLE body: quoted string or bare hex blob
_PROCTITLE_V = re.compile(r'\bproctitle=(?:"([^"]*)"|([\da-fA-F]+))')

_SYSCALL_EXECVE     = 59
_SYSCALL_EXIT_GROUP = 231
_MAX_BUFFER         = 100


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class AuditdParser:
    """Stateful auditd log line parser.

    Call :meth:`feed` for each raw line; collect the returned list of events.
    Call :meth:`flush` at EOF to drain any trailing buffered event that
    arrived without a closing EOE record.
    """

    def __init__(self) -> None:
        self._buf: dict[int, list[str]] = {}  # event_id → accumulated raw lines
        self._ts: dict[int, float] = {}        # event_id → first-seen timestamp

    def feed(self, line: str) -> list[ParsedProcessEvent]:
        """Accept one raw log line; return zero or more finalised events."""
        line = line.rstrip("\r\n")
        if not line:
            return []
        m = _HEADER.match(line)
        if m is None:
            return []

        rec_type = m.group(1)
        ts_float = float(m.group(2))
        event_id = int(m.group(3))

        if event_id not in self._buf:
            self._buf[event_id] = []
            self._ts[event_id] = ts_float

        buf = self._buf[event_id]
        buf.append(line)

        if rec_type == "EOE" or len(buf) >= _MAX_BUFFER:
            lines = self._buf.pop(event_id)
            ev_ts = self._ts.pop(event_id, ts_float)
            ev = _assemble(lines, event_id, ev_ts)
            return [ev] if ev is not None else []

        return []

    def flush(self) -> list[ParsedProcessEvent]:
        """Drain all buffered events (call at EOF or agent shutdown)."""
        result = []
        for eid, lines in list(self._buf.items()):
            ev_ts = self._ts.get(eid, 0.0)
            ev = _assemble(lines, eid, ev_ts)
            if ev is not None:
                result.append(ev)
        self._buf.clear()
        self._ts.clear()
        return result


# ---------------------------------------------------------------------------
# Internal assembly
# ---------------------------------------------------------------------------


def _assemble(
    lines: list[str], event_id: int, ts_float: float
) -> ParsedProcessEvent | None:
    """Turn a complete event's raw lines into a ParsedProcessEvent, or None."""
    syscall_body: str | None = None
    execve_body: str | None = None
    path_body: str | None = None
    proctitle_body: str | None = None

    for raw in lines:
        m = _HEADER.match(raw)
        if m is None:
            continue
        rec_type = m.group(1)
        body = m.group(4)

        if rec_type == "SYSCALL":
            syscall_body = body
        elif rec_type == "EXECVE":
            execve_body = body
        elif rec_type == "PATH" and path_body is None and _PATH_ITEM0.search(body):
            path_body = body
        elif rec_type == "PROCTITLE":
            proctitle_body = body
        # CWD, EOE, and other types are silently ignored

    if syscall_body is None:
        return None

    syscall_num = _int1(_SC_SYSCALL, syscall_body)
    if syscall_num not in (_SYSCALL_EXECVE, _SYSCALL_EXIT_GROUP):
        return None

    pid = _int1(_SC_PID, syscall_body)
    if pid is None:
        return None

    ppid    = _int1(_SC_PPID, syscall_body)
    uid     = _int1(_SC_UID, syscall_body)
    exit_v  = _int1(_SC_EXIT, syscall_body)
    exe     = _str1(_SC_EXE, syscall_body)

    # image: prefer exe from SYSCALL; fall back to PATH item=0 name
    image = exe
    if image is None and path_body is not None:
        pm = _PATH_ITEM0.search(path_body)
        if pm:
            image = pm.group(1)

    # cmdline: prefer EXECVE args; fall back to PROCTITLE
    cmdline: str | None = None
    if execve_body is not None:
        cmdline = _decode_execve(execve_body)
    if cmdline is None and proctitle_body is not None:
        cmdline = _decode_proctitle(proctitle_body)

    kind: Literal["process.created", "process.exited"]
    kind = "process.created" if syscall_num == _SYSCALL_EXECVE else "process.exited"

    return ParsedProcessEvent(
        kind=kind,
        occurred_at=datetime.fromtimestamp(ts_float, tz=UTC),
        pid=pid,
        ppid=ppid,
        user=_resolve_uid(uid),
        image=image,
        cmdline=cmdline,
        parent_image=None,
        exit_code=exit_v if kind == "process.exited" else None,
        audit_event_id=event_id,
        raw_lines=lines,
    )


def _int1(pat: re.Pattern[str], body: str) -> int | None:
    m = pat.search(body)
    return int(m.group(1)) if m else None


def _str1(pat: re.Pattern[str], body: str) -> str | None:
    m = pat.search(body)
    return m.group(1) if m else None


def _resolve_uid(uid: int | None) -> str | None:
    """Return the username for uid, falling back to the numeric string."""
    if uid is None:
        return None
    try:
        import pwd  # noqa: PLC0415
        return pwd.getpwuid(uid).pw_name
    except (KeyError, ImportError, AttributeError):
        return str(uid)


def _decode_execve(body: str) -> str | None:
    """Decode EXECVE record args into a space-joined command line."""
    argc_m = _EXECVE_ARGC.search(body)
    argc = int(argc_m.group(1)) if argc_m else None

    args: dict[int, str] = {}
    for m in _EXECVE_ARG.finditer(body):
        idx    = int(m.group(1))
        quoted = m.group(2)
        hexval = m.group(3)
        args[idx] = quoted if quoted is not None else _unhex(hexval)

    if not args:
        return None

    limit = argc if argc is not None else (max(args) + 1)
    return " ".join(args.get(i, "") for i in range(limit))


def _decode_proctitle(body: str) -> str | None:
    """Decode PROCTITLE value (quoted string or null-separated hex blob)."""
    m = _PROCTITLE_V.search(body)
    if m is None:
        return None
    quoted = m.group(1)
    hexval = m.group(2)
    if quoted is not None:
        return quoted
    if hexval:
        decoded = _unhex(hexval)
        return decoded.replace("\x00", " ").strip()
    return None


def _unhex(s: str) -> str:
    """Decode a bare hex string to UTF-8, returning the original on failure."""
    try:
        return bytes.fromhex(s).decode("utf-8", errors="replace")
    except ValueError:
        return s
