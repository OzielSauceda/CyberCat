"""conntrack ``/var/log/conntrack.log`` line parser.

Recognises one record family produced by
``conntrack -E -e NEW -o timestamp -o extended -o id``.

Example records (one per line; the format is self-contained — no buffering
required, unlike auditd):

  TCP NEW (with state token):
    [1777418334.439228]    [NEW] ipv4     2 tcp      6 120 SYN_SENT
    src=172.18.0.2 dst=172.66.147.243 sport=55068 dport=80 [UNREPLIED]
    src=172.66.147.243 dst=172.18.0.2 sport=80 dport=55068

  UDP NEW (no state token):
    [1777418275.833874]    [NEW] ipv4     2 udp      17 30
    src=10.0.0.5 dst=8.8.8.8 sport=44321 dport=53 [UNREPLIED]
    src=8.8.8.8 dst=10.0.0.5 sport=53 dport=44321

  ICMP NEW (type/code instead of port pair — port fields synthesized to 0):
    [1777418400.123]    [NEW] ipv4     2 icmp     1 30
    src=10.0.0.5 dst=8.8.8.8 type=8 code=0 id=4242 [UNREPLIED]
    src=8.8.8.8 dst=10.0.0.5 type=0 code=0 id=4242

  Optional trailing fields when ``-o id`` is in effect (varies by kernel /
  conntrack-tools version): ``mark=N use=N id=N``. Treated as optional.

Always uses the **first** (original-direction) ``src=...`` / ``dst=...`` /
``sport=...`` / ``dport=...`` tuple. The ``[UNREPLIED]`` reverse-direction
tuple is ignored.

Filtering at the parser:
  - Loopback (``127.0.0.0/8``, ``::1``) → dropped.
  - Link-local (``169.254.0.0/16``, ``fe80::/10``) → dropped.
  - Protocols other than TCP/UDP/ICMP (e.g. ``igmp``, ``gre``) → dropped.
  - Records that aren't ``[NEW]`` (``[UPDATE]``, ``[DESTROY]``) → dropped.

Anything malformed returns ``None``. The parser never raises on input.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


@dataclass(frozen=True)
class ParsedNetworkEvent:
    """Structured result of parsing one conntrack ``[NEW]`` line.

    All values come from the original-direction tuple (the half conntrack
    prints first); the ``[UNREPLIED]`` reverse-direction half is discarded.
    """

    kind: Literal["network.connection"]
    occurred_at: datetime
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    proto: str  # "tcp" | "udp" | "icmp"
    conntrack_id: int | None
    raw_line: str


# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------

# Leading "[<float-ts>]" (epoch seconds with microseconds), optional, surrounded
# by whitespace/tabs. ``-o timestamp`` always emits this; we still tolerate its
# absence for robustness.
_TIMESTAMP = re.compile(r"^\s*\[(?P<ts>\d+\.\d+)\]\s+")

# Marker after the timestamp.
_NEW_MARKER = re.compile(r"\[NEW\]")

# Protocol token. Either "ipv4 2 <proto> ..." (with -o extended) or
# "<proto> ..." (without). We accept both.
_PROTO = re.compile(
    r"\[NEW\]\s+(?:ipv4\s+\d+\s+|ipv6\s+\d+\s+)?(?P<proto>[a-z0-9_]+)\b"
)

# Original-direction five-tuple fields. We deliberately use the FIRST occurrence
# of each — conntrack prints original then reply (after `[UNREPLIED]`/`[ASSURED]`).
_SRC      = re.compile(r"\bsrc=(?P<v>\S+)")
_DST      = re.compile(r"\bdst=(?P<v>\S+)")
_SPORT    = re.compile(r"\bsport=(?P<v>\d+)")
_DPORT    = re.compile(r"\bdport=(?P<v>\d+)")
_ICMP_TYPE = re.compile(r"\btype=(?P<v>\d+)")

# Optional conntrack id (only when `-o id` is in effect AND the kernel emits it).
# Often missing — we fall back to a SHA256-of-line dedupe key in that case.
_CONNTRACK_ID = re.compile(r"\bid=(?P<v>\d+)")

_SUPPORTED_PROTOS = frozenset({"tcp", "udp", "icmp"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_line(line: str) -> ParsedNetworkEvent | None:
    """Parse one conntrack log line. Return ``None`` for non-NEW / filtered / malformed."""
    line = line.rstrip("\r\n")
    if not line:
        return None

    if not _NEW_MARKER.search(line):
        return None

    proto_m = _PROTO.search(line)
    if proto_m is None:
        return None
    proto = proto_m.group("proto").lower()
    if proto not in _SUPPORTED_PROTOS:
        return None

    src_m = _SRC.search(line)
    dst_m = _DST.search(line)
    if src_m is None or dst_m is None:
        return None
    src_ip = src_m.group("v")
    dst_ip = dst_m.group("v")

    if _should_drop(src_ip, dst_ip):
        return None

    if proto == "icmp":
        # ICMP records carry type/code instead of sport/dport. Synthesize port
        # numbers so the canonical event stays uniform: src_port=0, dst_port=type.
        type_m = _ICMP_TYPE.search(line)
        src_port = 0
        dst_port = int(type_m.group("v")) if type_m else 0
    else:
        sport_m = _SPORT.search(line)
        dport_m = _DPORT.search(line)
        if sport_m is None or dport_m is None:
            return None
        src_port = int(sport_m.group("v"))
        dst_port = int(dport_m.group("v"))

    occurred_at = _parse_ts(line)
    if occurred_at is None:
        return None

    id_m = _CONNTRACK_ID.search(line)
    conntrack_id = int(id_m.group("v")) if id_m else None

    return ParsedNetworkEvent(
        kind="network.connection",
        occurred_at=occurred_at,
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        proto=proto,
        conntrack_id=conntrack_id,
        raw_line=line,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_ts(line: str) -> datetime | None:
    """Pull the leading ``[epoch.us]`` timestamp; fall back to now() if absent."""
    m = _TIMESTAMP.match(line)
    if m is None:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.fromtimestamp(float(m.group("ts")), tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _should_drop(src_ip: str, dst_ip: str) -> bool:
    """Return True if either endpoint is loopback or link-local (v4 or v6)."""
    return _is_loopback_or_linklocal(src_ip) or _is_loopback_or_linklocal(dst_ip)


def _is_loopback_or_linklocal(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Unparseable address — be conservative and drop.
        return True
    return ip.is_loopback or ip.is_link_local
