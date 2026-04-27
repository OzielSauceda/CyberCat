from __future__ import annotations

from dataclasses import dataclass

from app.enums import ActionClassification, ActionKind

_MAX_REASON_LEN = 160

_TABLE: dict[ActionKind, tuple[ActionClassification, str]] = {
    ActionKind.tag_incident: (
        ActionClassification.auto_safe,
        "Adds a label to the incident record; no external effect.",
    ),
    ActionKind.elevate_severity: (
        ActionClassification.auto_safe,
        "Raises the incident severity in the DB; no external effect.",
    ),
    ActionKind.flag_host_in_lab: (
        ActionClassification.reversible,
        "Marks a lab host as under investigation; removable via revert.",
    ),
    ActionKind.invalidate_lab_session: (
        ActionClassification.reversible,
        "Invalidates a single lab session token; new logins still allowed.",
    ),
    ActionKind.quarantine_host_lab: (
        ActionClassification.disruptive,
        "Isolates the lab host from the lab network until manually released.",
    ),
    ActionKind.kill_process_lab: (
        ActionClassification.disruptive,
        "Terminates a running process on the lab host.",
    ),
    ActionKind.block_observable: (
        ActionClassification.reversible,
        "Adds an IP or hash to the deny list; removable via revert.",
    ),
    ActionKind.request_evidence: (
        ActionClassification.suggest_only,
        "Queues an evidence collection task; analyst must approve externally.",
    ),
}


@dataclass(frozen=True)
class ClassificationDecision:
    classification: ActionClassification
    reason: str


def classify(kind: ActionKind) -> ClassificationDecision:
    classification, reason = _TABLE[kind]
    assert len(reason) <= _MAX_REASON_LEN, f"reason too long for {kind}: {len(reason)}"
    return ClassificationDecision(classification=classification, reason=reason)
