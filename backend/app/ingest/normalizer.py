from __future__ import annotations

# Required top-level keys per event kind.
# A key ending in "?" is optional; all others must be present.
_REQUIRED: dict[str, frozenset[str]] = {
    "auth.failed":        frozenset({"user", "source_ip", "auth_type"}),
    "auth.succeeded":     frozenset({"user", "source_ip", "auth_type"}),
    "session.started":    frozenset({"user", "host", "session_id"}),
    "session.ended":      frozenset({"user", "host", "session_id"}),
    "process.created":    frozenset({"host", "pid", "ppid", "image", "cmdline"}),
    "process.exited":     frozenset({"host", "pid"}),
    "file.created":       frozenset({"host", "path"}),
    "network.connection": frozenset({"host", "src_ip", "dst_ip", "dst_port", "proto"}),
}

KNOWN_KINDS: frozenset[str] = frozenset(_REQUIRED)


def validate_normalized(kind: str, normalized: dict) -> list[str]:
    """Return a list of missing required field names, or [] if valid."""
    required = _REQUIRED.get(kind)
    if required is None:
        return []  # unknown kind is rejected before this is called
    missing = required - normalized.keys()
    return sorted(missing)
