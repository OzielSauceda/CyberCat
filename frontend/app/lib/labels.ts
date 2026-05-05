// Single source of truth for plain-language labels.
// Each entry: { label, plain, glossarySlug? }
//   label  — short visible label suitable for chips/headings
//   plain  — one-sentence definition for tooltips and help text
//   slug   — optional glossary key for "Read more →" deep-links

import type {
  ActionClassification,
  ActionKind,
  ActionStatus,
  AttackSource,
  DetectionRuleSource,
  EventSource,
  IncidentKind,
  IncidentStatus,
  RoleInIncident,
  Severity,
} from "./api"
import type { GlossarySlug } from "./glossary"

export interface Label {
  label: string
  plain: string
  slug?: GlossarySlug
}

export const SEVERITY_LABELS: Record<Severity, Label> = {
  info: {
    label: "Informational",
    plain: "Worth knowing about, but not a real threat on its own.",
    slug: "severity",
  },
  low: {
    label: "Low",
    plain: "Minor concern — keep an eye on it.",
    slug: "severity",
  },
  medium: {
    label: "Medium",
    plain: "Real signal worth investigating soon.",
    slug: "severity",
  },
  high: {
    label: "High",
    plain: "Likely real and likely important — handle today.",
    slug: "severity",
  },
  critical: {
    label: "Critical",
    plain: "Likely an active intrusion. Act now.",
    slug: "severity",
  },
}

export const SEVERITY_ABBREV: Record<Severity, string> = {
  info: "INFO",
  low: "LOW",
  medium: "MED",
  high: "HIGH",
  critical: "CRIT",
}

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, Label> = {
  new: {
    label: "Just opened",
    plain: "The case was just opened and hasn't been reviewed yet.",
    slug: "status",
  },
  triaged: {
    label: "Triaged",
    plain: "An analyst has reviewed it and decided it's worth investigating.",
    slug: "status",
  },
  investigating: {
    label: "Being investigated",
    plain: "Active work is underway on this case.",
    slug: "status",
  },
  contained: {
    label: "Contained",
    plain: "The threat has been isolated, but the root cause is still being addressed.",
    slug: "status",
  },
  resolved: {
    label: "Resolved",
    plain: "The root cause has been fixed.",
    slug: "status",
  },
  closed: {
    label: "Closed",
    plain: "No further action needed.",
    slug: "status",
  },
  reopened: {
    label: "Reopened",
    plain: "New signals have arrived — the case was reopened.",
    slug: "status",
  },
  merged: {
    label: "Merged",
    plain: "This incident was folded into another. Evidence and entities live on the parent now.",
    slug: "status",
  },
}

export const INCIDENT_KIND_LABELS: Record<IncidentKind, Label> = {
  identity_compromise: {
    label: "Suspicious sign-in activity",
    plain: "Signs that someone is trying — or has succeeded — to use an account that isn't theirs.",
  },
  endpoint_compromise: {
    label: "Suspicious activity on a machine",
    plain: "Unusual programs or behavior on a host that may indicate intrusion.",
  },
  identity_endpoint_chain: {
    label: "Compromised account acting on a machine",
    plain: "An account showed sign-in trouble and is now running unusual programs — strong sign someone else has it.",
  },
  unknown: {
    label: "Unclassified",
    plain: "The correlator opened a case but couldn't categorize it cleanly.",
  },
}

// Event kinds are open-ended strings on the wire; we map the known ones.
export const EVENT_KIND_LABELS: Record<string, Label> = {
  "auth.failed": {
    label: "Failed sign-in",
    plain: "Someone tried to log in and the password was wrong.",
    slug: "event-kind",
  },
  "auth.succeeded": {
    label: "Successful sign-in",
    plain: "Someone logged in successfully.",
    slug: "event-kind",
  },
  "session.started": {
    label: "Login session opened",
    plain: "A logged-in session was created on the host.",
    slug: "session",
  },
  "session.ended": {
    label: "Login session closed",
    plain: "A logged-in session ended.",
    slug: "session",
  },
  "process.created": {
    label: "Program started",
    plain: "A program was launched on the host.",
    slug: "event-kind",
  },
  "process.exited": {
    label: "Program exited",
    plain: "A running program finished.",
    slug: "event-kind",
  },
  "file.created": {
    label: "File created",
    plain: "A new file appeared on the host.",
    slug: "event-kind",
  },
  "file.modified": {
    label: "File modified",
    plain: "A file's contents were changed.",
    slug: "event-kind",
  },
  "network.connection": {
    label: "Network connection",
    plain: "A connection was opened between the host and another address.",
    slug: "event-kind",
  },
}

export function eventKindLabel(kind: string): Label {
  return (
    EVENT_KIND_LABELS[kind] ?? {
      label: kind,
      plain: "An event from the telemetry agent or Wazuh.",
      slug: "event-kind",
    }
  )
}

export const INCIDENT_EVENT_ROLE_LABELS: Record<RoleInIncident, Label> = {
  trigger: {
    label: "What started this",
    plain: "The event that opened this case.",
    slug: "role-in-incident",
  },
  supporting: {
    label: "Related signal",
    plain: "An event that helps confirm or build on the trigger.",
    slug: "role-in-incident",
  },
  context: {
    label: "Background",
    plain: "Surrounding activity included for context.",
    slug: "role-in-incident",
  },
}

export const ACTION_CLASSIFICATION_LABELS: Record<ActionClassification, Label> = {
  auto_safe: {
    label: "Safe to run automatically",
    plain: "No meaningful risk of disruption — CyberCat may run it without asking.",
    slug: "auto-safe",
  },
  suggest_only: {
    label: "Needs your approval",
    plain: "CyberCat will recommend it, but won't run it without you confirming.",
    slug: "suggest-only",
  },
  reversible: {
    label: "Can be undone",
    plain: "Has side effects, but CyberCat stores enough state to revert it.",
    slug: "reversible",
  },
  disruptive: {
    label: "May disrupt — confirm carefully",
    plain: "Has significant side effects that can't be automatically undone.",
    slug: "disruptive",
  },
}

export const ACTION_STATUS_LABELS: Record<ActionStatus, Label> = {
  proposed: {
    label: "Proposed",
    plain: "Suggested but not yet run.",
  },
  executed: {
    label: "Run",
    plain: "Successfully completed.",
  },
  failed: {
    label: "Failed",
    plain: "Tried to run but hit an error.",
  },
  skipped: {
    label: "Skipped",
    plain: "Not run — usually because preconditions weren't met.",
  },
  reverted: {
    label: "Reverted",
    plain: "Was run, then undone.",
  },
  partial: {
    label: "Partial",
    plain: "Some side effects took, others didn't.",
  },
}

export const ATTACK_SOURCE_LABELS: Record<AttackSource, Label> = {
  rule_derived: {
    label: "From a detection rule",
    plain: "This technique came from the tags on a Sigma or custom detection rule.",
  },
  correlator_inferred: {
    label: "Inferred by the correlator",
    plain: "The correlator added this technique based on the broader pattern, not a single rule.",
  },
}

export const EVENT_SOURCE_LABELS: Record<EventSource, Label> = {
  direct: {
    label: "CyberCat agent",
    plain: "The built-in cct-agent tailing sshd, auditd, and conntrack.",
    slug: "agent",
  },
  wazuh: {
    label: "Wazuh",
    plain: "Optional upstream telemetry from the Wazuh indexer.",
    slug: "wazuh",
  },
  seeder: {
    label: "Demo seeder",
    plain: "Seeded events from the built-in demo scenario.",
    slug: "source",
  },
}

export const DETECTION_RULE_SOURCE_LABELS: Record<DetectionRuleSource, Label> = {
  sigma: {
    label: "Sigma rule",
    plain: "A portable detection rule written in the Sigma YAML format.",
    slug: "sigma",
  },
  py: {
    label: "Custom",
    plain: "A custom Python detector built into CyberCat.",
    slug: "detection",
  },
}

// Plain-language gloss for ATT&CK tactics. Keyed by the tactic slug used in
// IncidentAttack.tactic (lowercase-with-dashes).
export const ATTACK_TACTIC_GLOSS: Record<string, string> = {
  reconnaissance: "Gathering information about a target.",
  "resource-development": "Setting up infrastructure for the attack.",
  "initial-access": "Getting their first foothold.",
  execution: "Running malicious code on a system.",
  persistence: "Keeping access across reboots and logouts.",
  "privilege-escalation": "Gaining higher access on a system.",
  "defense-evasion": "Hiding from detection tools.",
  "credential-access": "Stealing or guessing valid usernames and passwords.",
  discovery: "Looking around to learn the environment.",
  "lateral-movement": "Hopping from one machine to another inside the network.",
  collection: "Gathering data they want to steal.",
  "command-and-control": "Talking back to the attacker's server.",
  exfiltration: "Sending stolen data out.",
  impact: "Damaging, destroying, or holding data for ransom.",
}

// Helper: format an ActionKind value for display when no friendlier source is
// nearby. Prefers ACTION_FORMS.label from actionForms.ts where available; this
// is just the fallback humanizer.
export function humanizeKind(value: string): string {
  return value
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ")
}
