"""Recommended Response Actions engine (Phase 15).

Takes a fully loaded incident + related data and returns up to `max_results`
ranked, pre-filled RecommendedAction suggestions for the analyst UI.

Param-key contract (must stay in sync with ProposeActionModal form keys):
  block_observable:       {"kind": "ip"|"domain"|"hash"|"file", "value": "<value>"}
  quarantine_host_lab:    {"host": "<natural_key>"}
  invalidate_lab_session: {"user": "<natural_key>", "host": "<natural_key>"}
  flag_host_in_lab:       {"host": "<natural_key>"}
  request_evidence:       {"evidence_kind": "<kind>", "target_host": "<natural_key>"}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import Action, Entity, Incident, IncidentAttack
from app.enums import (
    ActionClassification,
    ActionKind,
    ActionStatus,
    EvidenceKind,
    IncidentEntityRole,
    IncidentKind,
)
from app.response.policy import classify

# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecommendedAction:
    kind: ActionKind
    params: dict[str, Any]
    summary: str
    rationale: str
    classification: ActionClassification
    classification_reason: str
    priority: int
    target_summary: str


# ---------------------------------------------------------------------------
# Level 1 — incident kind → base candidate list
# ---------------------------------------------------------------------------

_BASE_CANDIDATES: dict[IncidentKind, list[ActionKind]] = {
    IncidentKind.identity_compromise: [
        ActionKind.block_observable,
        ActionKind.invalidate_lab_session,
        ActionKind.flag_host_in_lab,
        ActionKind.request_evidence,
    ],
    IncidentKind.endpoint_compromise: [
        ActionKind.quarantine_host_lab,
        ActionKind.block_observable,
        ActionKind.flag_host_in_lab,
        ActionKind.request_evidence,
    ],
    IncidentKind.identity_endpoint_chain: [
        ActionKind.block_observable,
        ActionKind.quarantine_host_lab,
        ActionKind.invalidate_lab_session,
        ActionKind.flag_host_in_lab,
        ActionKind.request_evidence,
    ],
    IncidentKind.unknown: [
        ActionKind.request_evidence,
    ],
}

# Base score per action kind (higher = higher priority)
_BASE_SCORES: dict[ActionKind, int] = {
    ActionKind.block_observable: 50,
    ActionKind.quarantine_host_lab: 40,
    ActionKind.invalidate_lab_session: 30,
    ActionKind.flag_host_in_lab: 20,
    ActionKind.request_evidence: 10,
}

# Level 2 — (technique_prefix, action_kind, boost)
# Match via technique.startswith(prefix) so subtechniques inherit.
_TECHNIQUE_BOOSTS: list[tuple[str, ActionKind, int]] = [
    ("T1110", ActionKind.block_observable, 20),         # Brute Force → block source IP ↑↑
    ("T1078", ActionKind.invalidate_lab_session, 20),   # Valid Accounts → invalidate session ↑↑
    ("T1059", ActionKind.quarantine_host_lab, 10),      # Command & Scripting → quarantine ↑
    ("T1021", ActionKind.quarantine_host_lab, 20),      # Lateral Movement → quarantine ↑↑
    ("T1071", ActionKind.block_observable, 20),         # C2 → block IP ↑↑
    ("T1571", ActionKind.block_observable, 20),         # Non-standard port → block IP ↑↑
]

# Rationale templates keyed by (ActionKind, best-matched technique prefix or None)
_RATIONALES: dict[tuple[ActionKind, str | None], str] = {
    (ActionKind.block_observable, "T1110"): (
        "Brute-force pattern observed from {ip} — adding to deny list cuts off the attacker's source."
    ),
    (ActionKind.block_observable, "T1071"): (
        "Outbound C2 traffic detected to {ip} — denying it severs the channel."
    ),
    (ActionKind.block_observable, "T1571"): (
        "Outbound C2 traffic detected to {ip} — denying it severs the channel."
    ),
    (ActionKind.block_observable, None): (
        "Source IP {ip} is implicated in this incident; deny-listing prevents further activity."
    ),
    (ActionKind.quarantine_host_lab, "T1021"): (
        "Suspicious execution observed on {host} — isolating it prevents further spread."
    ),
    (ActionKind.quarantine_host_lab, "T1059"): (
        "Suspicious execution observed on {host} — isolating it prevents further spread."
    ),
    (ActionKind.quarantine_host_lab, None): (
        "Containment of {host} is reasonable while investigation proceeds."
    ),
    (ActionKind.invalidate_lab_session, None): (
        "Session for {user} on {host} should be killed if the credentials may have been compromised."
    ),
    (ActionKind.flag_host_in_lab, None): (
        "Mark {host} as under investigation to surface it in dashboards."
    ),
    (ActionKind.request_evidence, None): (
        "Collect a {evidence_kind} from {host} to support the investigation."
    ),
}

# Plain-language one-line summaries paired with each rationale entry. Same
# keying scheme: (ActionKind, technique-prefix-or-None). These are what the UI
# leads with; the longer technical rationale shows in a "Why this works" expander.
_SUMMARIES: dict[tuple[ActionKind, str | None], str] = {
    (ActionKind.block_observable, "T1110"): (
        "Block the address ({ip}) someone's been guessing passwords from."
    ),
    (ActionKind.block_observable, "T1071"): (
        "Block the address ({ip}) the host has been talking to — looks like attacker control traffic."
    ),
    (ActionKind.block_observable, "T1571"): (
        "Block the address ({ip}) the host has been talking to — looks like attacker control traffic."
    ),
    (ActionKind.block_observable, None): (
        "Block the address ({ip}) involved in this case so it can't act again."
    ),
    (ActionKind.quarantine_host_lab, "T1021"): (
        "Cut {host} off from the lab network so the attacker can't move further."
    ),
    (ActionKind.quarantine_host_lab, "T1059"): (
        "Cut {host} off from the lab network so the attacker can't move further."
    ),
    (ActionKind.quarantine_host_lab, None): (
        "Hold {host} aside while you investigate."
    ),
    (ActionKind.invalidate_lab_session, None): (
        "Sign {user} out on {host} in case the password is in the wrong hands."
    ),
    (ActionKind.flag_host_in_lab, None): (
        "Mark {host} as under investigation so it stands out in dashboards."
    ),
    (ActionKind.request_evidence, None): (
        "Pull a {evidence_kind} from {host} to help figure out what happened."
    ),
}


# These kinds are never surfaced as recommendations (admin/meta actions)
_EXCLUDED: frozenset[ActionKind] = frozenset({
    ActionKind.tag_incident,
    ActionKind.elevate_severity,
    ActionKind.kill_process_lab,
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _exec_key(kind: ActionKind, params: dict[str, Any]) -> tuple:
    """Equivalence key for already-executed filter.

    block_observable matches on (kind, value) only — two block actions on
    different IPs are distinct recommendations even though the kind is the same.
    All other actions use full params equality.
    """
    if kind == ActionKind.block_observable:
        return (kind, params.get("value", ""))
    return (kind, tuple(sorted(params.items())))


def _build_rationale(
    kind: ActionKind,
    best_prefix: str | None,
    params: dict[str, Any],
) -> str:
    key = (kind, best_prefix)
    template = _RATIONALES.get(key) or _RATIONALES.get((kind, None), "")
    return template.format(
        ip=params.get("value", ""),
        host=params.get("host") or params.get("target_host", ""),
        user=params.get("user", ""),
        evidence_kind=params.get("evidence_kind", EvidenceKind.triage_log.value),
    )


def _build_summary(
    kind: ActionKind,
    best_prefix: str | None,
    params: dict[str, Any],
) -> str:
    key = (kind, best_prefix)
    template = _SUMMARIES.get(key) or _SUMMARIES.get((kind, None), "")
    evidence_kind_raw = params.get("evidence_kind", EvidenceKind.triage_log.value)
    evidence_kind_plain = evidence_kind_raw.replace("_", " ")
    return template.format(
        ip=params.get("value", ""),
        host=params.get("host") or params.get("target_host", ""),
        user=params.get("user", ""),
        evidence_kind=evidence_kind_plain,
    )


def _build_target_summary(kind: ActionKind, params: dict[str, Any]) -> str:
    if kind == ActionKind.block_observable:
        return params.get("value", "")
    if kind in (ActionKind.quarantine_host_lab, ActionKind.flag_host_in_lab):
        return params.get("host", "")
    if kind == ActionKind.invalidate_lab_session:
        return f"{params.get('user', '')}@{params.get('host', '')}"
    if kind == ActionKind.request_evidence:
        return params.get("target_host", "")
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend_for_incident(
    incident: Incident,
    entities: list[tuple[Entity, IncidentEntityRole]],
    attack: list[IncidentAttack],
    actions: list[Action],
    *,
    max_results: int = 4,
) -> list[RecommendedAction]:
    """Return sorted pre-filled response recommendations for the given incident."""

    # 1. Bucket entities by incident role
    users: list[Entity] = []
    hosts: list[Entity] = []
    source_ips: list[Entity] = []
    observables: list[Entity] = []
    for entity, role in entities:
        if role == IncidentEntityRole.user:
            users.append(entity)
        elif role == IncidentEntityRole.host:
            hosts.append(entity)
        elif role == IncidentEntityRole.source_ip:
            source_ips.append(entity)
        elif role == IncidentEntityRole.observable:
            observables.append(entity)

    # 2. Build executed-filter set from non-reverted actions
    executed_keys: set[tuple] = set()
    for act in actions:
        if act.status not in (ActionStatus.reverted,):
            # Treat proposed/executed/failed/partial/skipped as "already accounted for"
            # Only reverted actions re-enter the recommendation pool
            if act.status in (ActionStatus.executed, ActionStatus.partial):
                executed_keys.add(_exec_key(act.kind, act.params))

    # 3. Collect technique tags
    technique_tags: list[str] = [a.technique for a in attack]

    # 4. Build scored candidates
    scored: list[tuple[int, ActionKind, dict[str, Any], str | None]] = []
    base_candidates = _BASE_CANDIDATES.get(incident.kind, [ActionKind.request_evidence])

    for kind in base_candidates:
        if kind in _EXCLUDED:
            continue

        # Build viable params sets for this kind
        candidate_params: list[dict[str, Any]] = []
        if kind == ActionKind.block_observable:
            for ip_entity in source_ips:
                candidate_params.append({"kind": "ip", "value": ip_entity.natural_key})
            for obs_entity in observables:
                obs_kind = obs_entity.attrs.get("kind", "ip")
                candidate_params.append({"kind": obs_kind, "value": obs_entity.natural_key})

        elif kind == ActionKind.quarantine_host_lab:
            if hosts:
                candidate_params.append({"host": hosts[0].natural_key})

        elif kind == ActionKind.invalidate_lab_session:
            if users and hosts:
                candidate_params.append({"user": users[0].natural_key, "host": hosts[0].natural_key})

        elif kind == ActionKind.flag_host_in_lab:
            if hosts:
                candidate_params.append({"host": hosts[0].natural_key})

        elif kind == ActionKind.request_evidence:
            if hosts:
                candidate_params.append({
                    "evidence_kind": EvidenceKind.triage_log.value,
                    "target_host": hosts[0].natural_key,
                })

        # Pick first params set not already executed
        chosen: dict[str, Any] | None = None
        for params in candidate_params:
            if _exec_key(kind, params) not in executed_keys:
                chosen = params
                break
        if chosen is None:
            continue

        # Score: base + all applicable technique boosts
        score = _BASE_SCORES.get(kind, 0)
        best_prefix: str | None = None
        for prefix, bkind, boost in _TECHNIQUE_BOOSTS:
            if bkind == kind and any(t.startswith(prefix) for t in technique_tags):
                score += boost
                if best_prefix is None:
                    best_prefix = prefix

        scored.append((score, kind, chosen, best_prefix))

    # 5. Sort by score desc, take top N, assign priority
    scored.sort(key=lambda x: -x[0])
    scored = scored[:max_results]

    results: list[RecommendedAction] = []
    for rank, (_, kind, params, best_prefix) in enumerate(scored, start=1):
        decision = classify(kind)
        results.append(RecommendedAction(
            kind=kind,
            params=params,
            summary=_build_summary(kind, best_prefix, params),
            rationale=_build_rationale(kind, best_prefix, params),
            classification=decision.classification,
            classification_reason=decision.reason,
            priority=rank,
            target_summary=_build_target_summary(kind, params),
        ))

    return results
