// Keep in sync with backend _ALLOWED_TRANSITIONS in
// backend/app/api/routers/incidents.py:47 and _REASON_REQUIRED at line 57.

import type { IncidentStatus } from "./api"

export const ALLOWED_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  new:          ["triaged", "closed"],
  triaged:      ["investigating", "closed"],
  investigating:["contained", "resolved", "closed"],
  contained:    ["resolved", "investigating", "closed"],
  resolved:     ["closed", "investigating"],
  closed:       [],
  reopened:     ["investigating"],
}

export const REASON_REQUIRED = new Set<IncidentStatus>(["contained", "resolved", "closed"])

export function allowedNextStatuses(from: IncidentStatus): IncidentStatus[] {
  return ALLOWED_TRANSITIONS[from] ?? []
}

export function reasonRequired(to: IncidentStatus): boolean {
  return REASON_REQUIRED.has(to)
}
