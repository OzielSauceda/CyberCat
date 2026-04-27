from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.enums import EventSource

logger = logging.getLogger(__name__)

_WHITELIST = {"authentication_failed", "authentication_success", "audit", "sysmon"}


@dataclass
class DecodedEvent:
    source: EventSource
    kind: str
    occurred_at: datetime
    raw: dict
    normalized: dict
    dedupe_key: str


def decode_wazuh_alert(alert: dict) -> DecodedEvent | None:
    """Map a Wazuh OpenSearch hit to a DecodedEvent, or return None to drop it.

    Caller must pass `alert` with `_id` merged in from the hit envelope.
    """
    rule_groups: list[str] = alert.get("rule", {}).get("groups", [])
    groups_set = set(rule_groups)

    if not groups_set.intersection(_WHITELIST):
        _drop(alert, "no_matching_group")
        return None

    ts_raw = alert.get("timestamp") or alert.get("@timestamp")
    occurred_at = _parse_ts(ts_raw)
    if occurred_at is None:
        _drop(alert, "unparseable_timestamp")
        return None

    dedupe_key = alert.get("_id")
    if not dedupe_key:
        _drop(alert, "missing_id")
        return None

    kind, normalized = _map_kind_and_normalized(alert, groups_set)
    if kind is None or normalized is None:
        return None

    return DecodedEvent(
        source=EventSource.wazuh,
        kind=kind,
        occurred_at=occurred_at,
        raw=alert,
        normalized=normalized,
        dedupe_key=dedupe_key,
    )


def _map_kind_and_normalized(
    alert: dict, groups_set: set[str]
) -> tuple[str, dict] | tuple[None, None]:
    data = alert.get("data", {})
    agent = alert.get("agent", {})

    # auth.failed — sshd authentication failure
    if ("authentication_failed" in groups_set and "sshd" in groups_set) or (
        "syslog" in groups_set and "sshd" in groups_set and "authentication_failed" in groups_set
    ):
        user = data.get("srcuser") or data.get("dstuser") or ""
        source_ip = data.get("srcip", "")
        if not source_ip:
            _drop(alert, "missing_srcip_for_auth_failed")
            return None, None
        return "auth.failed", {
            "user": user,
            "source_ip": source_ip,
            "auth_type": "ssh",
        }

    # auth.succeeded — sshd authentication success
    if "authentication_success" in groups_set and "sshd" in groups_set:
        user = data.get("dstuser") or data.get("srcuser") or ""
        source_ip = data.get("srcip", "")
        if not source_ip:
            _drop(alert, "missing_srcip_for_auth_succeeded")
            return None, None
        return "auth.succeeded", {
            "user": user,
            "source_ip": source_ip,
            "auth_type": "ssh",
        }

    # process.created — auditd EXECVE (Linux)
    if "audit" in groups_set:
        audit = data.get("audit", {})
        audit_type = audit.get("type", "")
        if audit_type != "EXECVE" and "audit_command" not in groups_set:
            _drop(alert, "audit_not_execve")
            return None, None
        host = agent.get("name", "")
        if not host:
            _drop(alert, "missing_agent_name_for_process_created")
            return None, None
        cmdline = audit.get("command") or _join_args(audit)
        return "process.created", {
            "host": host,
            "pid": _int_or_zero(audit.get("pid")),
            "ppid": _int_or_zero(audit.get("ppid")),
            "image": audit.get("exe", ""),
            "cmdline": cmdline,
            "user": "",
        }

    # process.created — Sysmon EventID 1 (Windows)
    if "sysmon" in groups_set:
        win = data.get("win", {})
        system = win.get("system", {})
        eventdata = win.get("eventdata", {})
        if system.get("eventID") != "1":
            _drop(alert, "sysmon_not_eid1")
            return None, None
        host = agent.get("name", "") or system.get("computer", "")
        if not host:
            _drop(alert, "missing_host_for_sysmon_process_created")
            return None, None
        return "process.created", {
            "host": host,
            "pid": _int_or_zero(eventdata.get("processId")),
            "ppid": _int_or_zero(eventdata.get("parentProcessId")),
            "image": eventdata.get("image", ""),
            "cmdline": eventdata.get("commandLine", ""),
            "user": eventdata.get("user", ""),
        }

    _drop(alert, "unmatched_group_combination")
    return None, None


def _join_args(audit: dict) -> str:
    args = []
    for key in ("a0", "a1", "a2", "a3", "a4"):
        val = audit.get(key)
        if val:
            args.append(val)
    return " ".join(args)


def _int_or_zero(val: object) -> int:
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_ts(raw: object) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        from datetime import timezone as tz
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=tz.utc)
    except (ValueError, TypeError):
        return None


def _drop(alert: dict, reason: str) -> None:
    rule_id = alert.get("rule", {}).get("id", "unknown")
    logger.warning(
        "event.source=wazuh event.dropped rule.id=%s reason=%s",
        rule_id,
        reason,
    )
