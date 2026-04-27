// Types mirror backend/app/api/schemas/incidents.py and backend/app/enums.py exactly.
// Update both sides whenever the contract changes.

const BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "")

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type Severity = "info" | "low" | "medium" | "high" | "critical"
export type IncidentStatus =
  | "new"
  | "triaged"
  | "investigating"
  | "contained"
  | "resolved"
  | "closed"
  | "reopened"
export type IncidentKind =
  | "identity_compromise"
  | "endpoint_compromise"
  | "identity_endpoint_chain"
  | "unknown"
export type EntityKind = "user" | "host" | "ip" | "process" | "file" | "observable"
export type ActionKind =
  | "tag_incident"
  | "elevate_severity"
  | "flag_host_in_lab"
  | "quarantine_host_lab"
  | "invalidate_lab_session"
  | "block_observable"
  | "kill_process_lab"
  | "request_evidence"
export type ActionClassification = "auto_safe" | "suggest_only" | "reversible" | "disruptive"
export type ActionStatus = "proposed" | "executed" | "failed" | "skipped" | "reverted" | "partial"
export type ActionResult = "ok" | "fail" | "skipped" | "partial"
export type RoleInIncident = "trigger" | "supporting" | "context"
export type EventSource = "wazuh" | "direct" | "seeder"
export type AttackSource = "rule_derived" | "correlator_inferred"
export type DetectionRuleSource = "sigma" | "py"

// ---------------------------------------------------------------------------
// Incident list
// ---------------------------------------------------------------------------

export interface IncidentSummary {
  id: string
  title: string
  kind: IncidentKind
  status: IncidentStatus
  severity: Severity
  confidence: number
  opened_at: string
  updated_at: string
  entity_count: number
  detection_count: number
  event_count: number
  primary_user: string | null
  primary_host: string | null
}

export interface IncidentList {
  items: IncidentSummary[]
  next_cursor: string | null
}

// ---------------------------------------------------------------------------
// Incident detail
// ---------------------------------------------------------------------------

export interface EntityRef {
  id: string
  kind: EntityKind
  natural_key: string
  attrs: Record<string, unknown>
  role_in_incident: string
}

export interface DetectionRef {
  id: string
  rule_id: string
  rule_source: DetectionRuleSource
  rule_version: string
  severity_hint: Severity
  confidence_hint: number
  attack_tags: string[]
  matched_fields: Record<string, unknown>
  event_id: string
  created_at: string
}

export interface TimelineEvent {
  id: string
  occurred_at: string
  kind: string
  source: EventSource
  normalized: Record<string, unknown>
  role_in_incident: RoleInIncident
  entity_ids: string[]
}

export interface AttackRef {
  tactic: string
  technique: string
  subtechnique: string | null
  source: AttackSource
}

export interface ActionLogSummary {
  executed_at: string
  executed_by: string
  result: ActionResult
  reason: string | null
  reversal_info: Record<string, unknown> | null
}

export interface ActionSummary {
  id: string
  kind: string
  classification: ActionClassification
  classification_reason: string | null
  status: ActionStatus
  params: Record<string, unknown>
  proposed_by: "system" | "analyst"
  proposed_at: string
  last_log: ActionLogSummary | null
}

export interface TransitionRef {
  from_status: IncidentStatus | null
  to_status: IncidentStatus
  actor: string
  reason: string | null
  at: string
}

export interface NoteRef {
  id: string
  body: string
  author: string
  created_at: string
}

export interface IncidentDetail {
  id: string
  title: string
  kind: IncidentKind
  status: IncidentStatus
  severity: Severity
  confidence: number
  rationale: string
  opened_at: string
  updated_at: string
  closed_at: string | null
  correlator_rule: string
  correlator_version: string
  entities: EntityRef[]
  detections: DetectionRef[]
  timeline: TimelineEvent[]
  attack: AttackRef[]
  actions: ActionSummary[]
  transitions: TransitionRef[]
  notes: NoteRef[]
}

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
    credentials: "include",
  })
  if (!res.ok) {
    if (
      res.status === 401 &&
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.assign(
        `/login?next=${encodeURIComponent(window.location.pathname)}`
      )
    }
    let code = `http_${res.status}`
    let message = res.statusText
    let details: unknown
    try {
      const body = (await res.json()) as {
        error?: { code?: string; message?: string; details?: unknown }
        detail?: { error?: { code?: string; message?: string; details?: unknown } }
      }
      const err = body.error ?? body.detail?.error
      if (err) {
        code = err.code ?? code
        message = err.message ?? message
        details = err.details
      }
    } catch {
      // ignore parse failure; use defaults
    }
    throw new ApiError(res.status, code, message, details)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export interface ListIncidentsParams {
  status?: string
  severity_gte?: string
  entity_id?: string
  opened_after?: string
  limit?: number
  cursor?: string
}

export function listIncidents(params: ListIncidentsParams = {}): Promise<IncidentList> {
  const q = new URLSearchParams()
  if (params.status) q.set("status", params.status)
  if (params.severity_gte) q.set("severity_gte", params.severity_gte)
  if (params.entity_id) q.set("entity_id", params.entity_id)
  if (params.opened_after) q.set("opened_after", params.opened_after)
  if (params.limit != null) q.set("limit", String(params.limit))
  if (params.cursor) q.set("cursor", params.cursor)
  const qs = q.toString()
  return request<IncidentList>(`/v1/incidents${qs ? `?${qs}` : ""}`)
}

export function getIncident(id: string): Promise<IncidentDetail> {
  return request<IncidentDetail>(`/v1/incidents/${id}`)
}

// ---------------------------------------------------------------------------
// Write paths — Phase 5b
// ---------------------------------------------------------------------------

export interface TransitionIn {
  to_status: IncidentStatus
  reason?: string
}

export interface TransitionResponse {
  incident_id: string
  from_status: IncidentStatus | null
  to_status: IncidentStatus
  at: string
}

export interface NoteIn {
  body: string
}

export interface ProposeActionIn {
  incident_id: string
  kind: ActionKind
  params: Record<string, unknown>
}

export interface ActionExecuteResponse {
  action: ActionSummary
  log: ActionLogSummary
}

export type LabAssetKind = "user" | "host" | "ip" | "observable"

export interface LabAsset {
  id: string
  kind: LabAssetKind
  natural_key: string
  registered_at: string
  notes: string | null
}

export interface LabAssetList {
  items: LabAsset[]
  next_cursor: string | null
}

export function createTransition(id: string, body: TransitionIn): Promise<TransitionResponse> {
  return request<TransitionResponse>(`/v1/incidents/${id}/transitions`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function createNote(id: string, body: NoteIn): Promise<NoteRef> {
  return request<NoteRef>(`/v1/incidents/${id}/notes`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export interface ListActionsParams {
  incident_id?: string
  status?: ActionStatus
  classification?: ActionClassification
  kind?: ActionKind
  since?: string
  limit?: number
}

export function listActions(params: ListActionsParams = {}): Promise<{ items: ActionSummary[]; next_cursor: string | null }> {
  const q = new URLSearchParams()
  if (params.incident_id) q.set("incident_id", params.incident_id)
  if (params.status) q.set("status", params.status)
  if (params.classification) q.set("classification", params.classification)
  if (params.kind) q.set("kind", params.kind)
  if (params.since) q.set("since", params.since)
  if (params.limit != null) q.set("limit", String(params.limit))
  const qs = q.toString()
  return request(`/v1/responses${qs ? `?${qs}` : ""}`)
}

export function proposeAction(body: ProposeActionIn): Promise<{ action: ActionSummary }> {
  return request<{ action: ActionSummary }>("/v1/responses", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function executeAction(actionId: string): Promise<ActionExecuteResponse> {
  return request<ActionExecuteResponse>(`/v1/responses/${actionId}/execute`, {
    method: "POST",
  })
}

export function revertAction(actionId: string): Promise<ActionExecuteResponse> {
  return request<ActionExecuteResponse>(`/v1/responses/${actionId}/revert`, {
    method: "POST",
  })
}

export function listLabAssets(params?: { kind?: LabAssetKind }): Promise<LabAsset[]> {
  const q = new URLSearchParams()
  if (params?.kind) q.set("kind", params.kind)
  const qs = q.toString()
  return request<LabAsset[]>(`/v1/lab/assets${qs ? `?${qs}` : ""}`)
}

export interface LabAssetIn {
  kind: LabAssetKind
  natural_key: string
  notes?: string
}

export function createLabAsset(body: LabAssetIn): Promise<LabAsset> {
  return request<LabAsset>("/v1/lab/assets", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function deleteLabAsset(id: string): Promise<void> {
  return request<void>(`/v1/lab/assets/${id}`, { method: "DELETE" })
}

// ---------------------------------------------------------------------------
// ATT&CK catalog — Phase 6b
// ---------------------------------------------------------------------------

export interface AttackEntry {
  id: string
  name: string
  kind: "tactic" | "technique" | "subtechnique"
  parent: string | null
  url: string
}

export interface AttackCatalog {
  version: string
  entries: AttackEntry[]
}

export function getAttackCatalog(): Promise<AttackCatalog> {
  return request<AttackCatalog>("/v1/attack/catalog")
}

// ---------------------------------------------------------------------------
// Entity detail — Phase 6b
// ---------------------------------------------------------------------------

export interface EntityTimelineEvent {
  id: string
  occurred_at: string
  kind: string
  normalized: Record<string, unknown>
}

export interface EntityIncidentSummary {
  id: string
  title: string
  kind: IncidentKind
  status: IncidentStatus
  severity: Severity
  confidence: number
  opened_at: string
  updated_at: string
}

export interface EntityDetail {
  id: string
  kind: EntityKind
  natural_key: string
  attrs: Record<string, unknown>
  first_seen: string
  last_seen: string
  recent_events: EntityTimelineEvent[]
  related_incidents: EntityIncidentSummary[]
}

export function getEntity(id: string): Promise<EntityDetail> {
  return request<EntityDetail>(`/v1/entities/${id}`)
}

export function lookupEntity(kind: EntityKind, natural_key: string): Promise<EntityDetail> {
  const q = new URLSearchParams({ kind, natural_key })
  return request<EntityDetail>(`/v1/entities?${q}`)
}

// ---------------------------------------------------------------------------
// Detections list — Phase 6b
// ---------------------------------------------------------------------------

export interface DetectionItem {
  id: string
  rule_id: string
  rule_source: DetectionRuleSource
  rule_version: string
  severity_hint: Severity
  confidence_hint: number
  attack_tags: string[]
  matched_fields: Record<string, unknown>
  event_id: string
  incident_id: string | null
  created_at: string
}

export interface DetectionList {
  items: DetectionItem[]
  next_cursor: string | null
}

export interface ListDetectionsParams {
  incident_id?: string
  rule_id?: string
  rule_source?: DetectionRuleSource
  since?: string
  limit?: number
  cursor?: string
}

export function listDetections(params: ListDetectionsParams = {}): Promise<DetectionList> {
  const q = new URLSearchParams()
  if (params.incident_id) q.set("incident_id", params.incident_id)
  if (params.rule_id) q.set("rule_id", params.rule_id)
  if (params.rule_source) q.set("rule_source", params.rule_source)
  if (params.since) q.set("since", params.since)
  if (params.limit != null) q.set("limit", String(params.limit))
  if (params.cursor) q.set("cursor", params.cursor)
  const qs = q.toString()
  return request<DetectionList>(`/v1/detections${qs ? `?${qs}` : ""}`)
}

// ---------------------------------------------------------------------------
// Evidence requests — Phase 9A
// ---------------------------------------------------------------------------

export type EvidenceStatus = "open" | "collected" | "dismissed"
export type EvidenceKind = "triage_log" | "process_list" | "network_connections" | "memory_snapshot"

export interface EvidenceRequest {
  id: string
  incident_id: string
  target_host_entity_id: string | null
  kind: EvidenceKind
  status: EvidenceStatus
  requested_at: string
  collected_at: string | null
  payload_url: string | null
}

export interface EvidenceRequestList {
  items: EvidenceRequest[]
}

export function listEvidenceRequests(incidentId: string): Promise<EvidenceRequestList> {
  return request<EvidenceRequestList>(`/v1/evidence-requests?incident_id=${incidentId}`)
}

export function collectEvidenceRequest(id: string): Promise<EvidenceRequest> {
  return request<EvidenceRequest>(`/v1/evidence-requests/${id}/collect`, { method: "POST" })
}

export function dismissEvidenceRequest(id: string): Promise<EvidenceRequest> {
  return request<EvidenceRequest>(`/v1/evidence-requests/${id}/dismiss`, { method: "POST" })
}

// ---------------------------------------------------------------------------
// Blocked observables — Phase 9A
// ---------------------------------------------------------------------------

export type BlockableKind = "ip" | "domain" | "hash" | "file"

export interface BlockedObservable {
  id: string
  kind: BlockableKind
  value: string
  blocked_at: string
  active: boolean
}

export interface BlockedObservableList {
  items: BlockedObservable[]
}

export function listBlockedObservables(params?: { active?: boolean; value?: string }): Promise<BlockedObservableList> {
  const q = new URLSearchParams()
  if (params?.active != null) q.set("active", String(params.active))
  if (params?.value) q.set("value", params.value)
  const qs = q.toString()
  return request<BlockedObservableList>(`/v1/blocked-observables${qs ? `?${qs}` : ""}`)
}
