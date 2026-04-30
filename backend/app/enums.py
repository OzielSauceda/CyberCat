from __future__ import annotations

import enum


class EntityKind(str, enum.Enum):
    user = "user"
    host = "host"
    ip = "ip"
    process = "process"
    file = "file"
    observable = "observable"


class EventSource(str, enum.Enum):
    wazuh = "wazuh"
    direct = "direct"
    seeder = "seeder"


class EventEntityRole(str, enum.Enum):
    actor = "actor"
    target = "target"
    source_ip = "source_ip"
    host = "host"
    process = "process"
    parent_process = "parent_process"
    file = "file"
    observable = "observable"


class DetectionRuleSource(str, enum.Enum):
    sigma = "sigma"
    py = "py"


class Severity(str, enum.Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentKind(str, enum.Enum):
    identity_compromise = "identity_compromise"
    endpoint_compromise = "endpoint_compromise"
    identity_endpoint_chain = "identity_endpoint_chain"
    unknown = "unknown"


class IncidentStatus(str, enum.Enum):
    new = "new"
    triaged = "triaged"
    investigating = "investigating"
    contained = "contained"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class IncidentEventRole(str, enum.Enum):
    trigger = "trigger"
    supporting = "supporting"
    context = "context"


class IncidentEntityRole(str, enum.Enum):
    user = "user"
    host = "host"
    source_ip = "source_ip"
    observable = "observable"
    target_host = "target_host"
    target_user = "target_user"


class AttackSource(str, enum.Enum):
    rule_derived = "rule_derived"
    correlator_inferred = "correlator_inferred"


class ActionKind(str, enum.Enum):
    tag_incident = "tag_incident"
    elevate_severity = "elevate_severity"
    flag_host_in_lab = "flag_host_in_lab"
    quarantine_host_lab = "quarantine_host_lab"
    invalidate_lab_session = "invalidate_lab_session"
    block_observable = "block_observable"
    kill_process_lab = "kill_process_lab"
    request_evidence = "request_evidence"


class ActionClassification(str, enum.Enum):
    auto_safe = "auto_safe"
    suggest_only = "suggest_only"
    reversible = "reversible"
    disruptive = "disruptive"


class ActionProposedBy(str, enum.Enum):
    system = "system"
    analyst = "analyst"


class ActionStatus(str, enum.Enum):
    proposed = "proposed"
    executed = "executed"
    failed = "failed"
    skipped = "skipped"
    reverted = "reverted"
    partial = "partial"


class ActionResult(str, enum.Enum):
    ok = "ok"
    fail = "fail"
    skipped = "skipped"
    partial = "partial"


class LabAssetKind(str, enum.Enum):
    user = "user"
    host = "host"
    ip = "ip"
    observable = "observable"


class BlockableKind(str, enum.Enum):
    ip = "ip"
    domain = "domain"
    hash = "hash"
    file = "file"


class EvidenceKind(str, enum.Enum):
    triage_log = "triage_log"
    process_list = "process_list"
    network_connections = "network_connections"
    memory_snapshot = "memory_snapshot"


class EvidenceStatus(str, enum.Enum):
    open = "open"
    collected = "collected"
    dismissed = "dismissed"
