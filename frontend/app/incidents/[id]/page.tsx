"use client"

import Link from "next/link"
import { use, useCallback, useState } from "react"
import { AttackTag } from "../../components/AttackTag"
import { ConfidenceBar } from "../../components/ConfidenceBar"
import { EmptyState } from "../../components/EmptyState"
import { EntityChip } from "../../components/EntityChip"
import { ErrorState } from "../../components/ErrorState"
import { JsonBlock } from "../../components/JsonBlock"
import { Panel } from "../../components/Panel"
import { RelativeTime } from "../../components/RelativeTime"
import { SeverityBadge } from "../../components/SeverityBadge"
import { SkeletonRow } from "../../components/Skeleton"
import { StatusPill } from "../../components/StatusPill"
import { TransitionMenu } from "../../components/TransitionMenu"
import {
  ApiError,
  getIncident,
  type ActionKind,
  type AttackRef,
  type EntityKind,
  type EntityRef,
  type IncidentDetail,
  type RecommendedAction,
  type TimelineEvent,
} from "../../lib/api"
import { useAttackEntry } from "../../lib/attackCatalog"
import { useStream } from "../../lib/useStream"
import { EvidenceRequestsPanel } from "../../components/EvidenceRequestsPanel"
import { JargonTerm } from "../../components/JargonTerm"
import { ActionsPanel } from "./ActionsPanel"
import { AttackKillChainPanel } from "./AttackKillChainPanel"
import { EntityGraphPanel } from "./EntityGraphPanel"
import { IncidentTimelineViz } from "./IncidentTimelineViz"
import { NotesPanel } from "./NotesPanel"
import { ProposeActionModal } from "./ProposeActionModal"
import { RecommendedActionsPanel } from "./RecommendedActionsPanel"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function s(v: unknown): string {
  return typeof v === "string" ? v : ""
}

function getEventSummary(event: TimelineEvent): string {
  const n = event.normalized
  switch (event.kind) {
    case "auth.failed":
    case "auth.succeeded":
      return [s(n.user), s(n.source_ip)].filter(Boolean).join(" from ")
    case "session.started":
    case "session.ended":
      return [s(n.user), "→", s(n.host), s(n.session_id) ? `(${s(n.session_id)})` : ""]
        .filter(Boolean).join(" ")
    case "process.created": {
      const image = s(n.image).split("\\").pop() ?? s(n.image)
      const pid = n.pid ? `pid:${n.pid}` : ""
      return [image, pid].filter(Boolean).join(" ")
    }
    case "file.created":
    case "file.modified":
      return s(n.path) || s(n.name)
    case "network.connection":
      return [s(n.src_ip), "→", s(n.dst_ip), n.dst_port ? `:${n.dst_port}` : ""]
        .filter(Boolean).join(" ")
    default:
      return ""
  }
}

function groupEventsByEntity(
  events: TimelineEvent[],
  entities: EntityRef[],
): Array<{ entity: EntityRef | null; events: TimelineEvent[] }> {
  const entityMap = new Map(entities.map((e) => [e.id, e]))
  const order: string[] = []
  const groups = new Map<string, { entity: EntityRef | null; events: TimelineEvent[] }>()
  for (const event of events) {
    let assigned = false
    for (const eid of event.entity_ids) {
      const entity = entityMap.get(eid)
      if (entity) {
        if (!groups.has(entity.id)) { groups.set(entity.id, { entity, events: [] }); order.push(entity.id) }
        groups.get(entity.id)!.events.push(event)
        assigned = true; break
      }
    }
    if (!assigned) {
      if (!groups.has("__other__")) { groups.set("__other__", { entity: null, events: [] }); order.push("__other__") }
      groups.get("__other__")!.events.push(event)
    }
  }
  return order.map((k) => groups.get(k)!)
}

const roleStyles: Record<string, string> = {
  trigger:    "text-dossier-redaction border-dossier-redaction/40 bg-red-950/40",
  supporting: "text-dossier-ink/60 border-dossier-paperEdge bg-dossier-stamp",
  context:    "text-dossier-ink/35 border-dossier-paperEdge/60 bg-dossier-stamp/60",
}

// ---------------------------------------------------------------------------
// Sub-panels
// ---------------------------------------------------------------------------

function TimelinePanel({ events, entities }: { events: TimelineEvent[]; entities: EntityRef[] }) {
  const [byEntity, setByEntity] = useState(true)

  const renderEvent = (ev: TimelineEvent, showEntityChips = true) => {
    const summary = getEventSummary(ev)
    const linkedEntities = entities.filter((e) => ev.entity_ids.includes(e.id))
    return (
      <div key={ev.id} className="flex flex-col gap-1 border-b border-dossier-paperEdge py-2.5 last:border-0">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-dossier-evidenceTape/50">
            {new Date(ev.occurred_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
          <span className="font-mono font-medium text-dossier-ink">{ev.kind}</span>
          <span className="rounded border border-dossier-paperEdge bg-dossier-stamp px-1 py-0.5 font-mono text-dossier-ink/40">
            {ev.source}
          </span>
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-case font-semibold uppercase tracking-wider ${roleStyles[ev.role_in_incident] ?? roleStyles.context}`}>
            {ev.role_in_incident}
          </span>
          {summary && <span className="font-mono text-dossier-ink/60 ml-auto text-right">{summary}</span>}
        </div>
        {showEntityChips && linkedEntities.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {linkedEntities.map((e) => (
              <EntityChip key={e.id} id={e.id} kind={e.kind as EntityKind} naturalKey={e.natural_key} />
            ))}
          </div>
        )}
        <JsonBlock data={ev.normalized} />
      </div>
    )
  }

  return (
    <Panel title="Event Timeline" count={events.length}>
      <div className="mb-3 flex gap-1">
        {[{ id: true, label: "By entity" }, { id: false, label: "Chronological" }].map(({ id, label }) => (
          <button
            key={String(id)}
            onClick={() => setByEntity(id)}
            className={`rounded border px-2.5 py-1 font-case text-[10px] font-semibold uppercase tracking-wider transition-colors ${
              byEntity === id
                ? "border-dossier-evidenceTape/40 bg-dossier-evidenceTape/8 text-dossier-evidenceTape"
                : "border-dossier-paperEdge text-dossier-ink/40 hover:text-dossier-ink/70"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {events.length === 0 ? <EmptyState title="No events linked" /> : byEntity ? (
        groupEventsByEntity(events, entities).map(({ entity, events: evs }) => (
          <div key={entity?.id ?? "__other__"} className="mb-4 last:mb-0">
            <div className="mb-1.5 flex items-center gap-2">
              {entity
                ? <EntityChip id={entity.id} kind={entity.kind as EntityKind} naturalKey={entity.natural_key} role={entity.role_in_incident} />
                : <span className="font-mono text-[10px] text-dossier-ink/30">other</span>}
              <span className="font-mono text-[10px] text-dossier-ink/25">{evs.length} events</span>
            </div>
            <div className="rounded-lg border border-dossier-paperEdge bg-dossier-stamp px-3">
              {evs.map((ev) => renderEvent(ev, false))}
            </div>
          </div>
        ))
      ) : (
        <div className="rounded-lg border border-dossier-paperEdge bg-dossier-stamp px-3">
          {events.map((ev) => renderEvent(ev))}
        </div>
      )}
    </Panel>
  )
}

function DetectionsPanel({ detections }: { detections: IncidentDetail["detections"] }) {
  return (
    <Panel title="Detection Matches" count={detections.length}>
      {detections.length === 0 ? <EmptyState title="No detections" /> : (
        <div className="space-y-3">
          {detections.map((d) => (
            <div key={d.id} className="rounded-lg border border-dossier-paperEdge bg-dossier-stamp p-3">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span className="font-mono text-sm font-medium text-dossier-ink">{d.rule_id}</span>
                <span className={`rounded border px-1.5 py-0.5 font-case text-[9px] font-semibold uppercase tracking-wider ${
                  d.rule_source === "sigma"
                    ? "border-violet-700/50 bg-violet-950/50 text-violet-400"
                    : "border-sky-700/50 bg-sky-950/50 text-sky-400"
                }`}>{d.rule_source}</span>
                <span className="font-mono text-[10px] text-dossier-ink/30">v{d.rule_version}</span>
              </div>
              <div className="flex flex-wrap items-center gap-3 mb-2">
                <SeverityBadge severity={d.severity_hint} />
                <span className="flex items-center gap-1.5 font-mono text-xs text-dossier-ink/50">
                  confidence <ConfidenceBar value={d.confidence_hint} />
                </span>
              </div>
              {d.attack_tags.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {d.attack_tags.map((tag) => (
                    <AttackTagById key={tag} id={tag} source="rule_derived" />
                  ))}
                </div>
              )}
              <JsonBlock data={d.matched_fields} />
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function EntitiesPanel({ entities }: { entities: EntityRef[] }) {
  const grouped = entities.reduce<Partial<Record<EntityKind, EntityRef[]>>>((acc, e) => {
    const k = e.kind as EntityKind
    if (!acc[k]) acc[k] = []
    acc[k]!.push(e)
    return acc
  }, {})

  return (
    <Panel title="Involved Entities" count={entities.length}>
      {entities.length === 0 ? <EmptyState title="No entities linked" /> : (
        <div className="space-y-3">
          {(Object.entries(grouped) as [EntityKind, EntityRef[]][]).map(([kind, ents]) => (
            <div key={kind}>
              <p className="mb-1.5 font-case text-[9px] uppercase tracking-widest text-dossier-evidenceTape/40">{kind}</p>
              <div className="space-y-2">
                {ents.map((e) => (
                  <div key={e.id} className="rounded-lg border border-dossier-paperEdge bg-dossier-stamp p-3">
                    <div className="flex flex-wrap items-center gap-2 mb-1.5">
                      <EntityChip id={e.id} kind={kind} naturalKey={e.natural_key} />
                      <span className="font-case text-[9px] uppercase tracking-wider text-dossier-ink/35">{e.role_in_incident}</span>
                    </div>
                    <JsonBlock data={e.attrs} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function AttackTagById({ id, source }: { id: string; source: AttackRef["source"] }) {
  const entry = useAttackEntry(id)
  const hasDot = id.includes(".")
  const technique = hasDot ? id.split(".")[0] : id
  const subtechnique = hasDot ? id : null
  return <AttackTag technique={technique} subtechnique={subtechnique} source={source} name={entry?.name} />
}

function TransitionsPanel({ transitions }: { transitions: IncidentDetail["transitions"] }) {
  return (
    <Panel title="Status History" count={transitions.length}>
      {transitions.length === 0 ? <EmptyState title="No transitions recorded" /> : (
        <ol className="relative ml-2 space-y-4 border-l border-dossier-paperEdge pl-4">
          {transitions.map((t, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[1.4rem] mt-0.5 flex h-3 w-3 items-center justify-center">
                <span className="h-1.5 w-1.5 rounded-full bg-dossier-evidenceTape/40" />
              </span>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {t.from_status ? <StatusPill status={t.from_status} /> : <span className="text-dossier-ink/25">—</span>}
                <span className="text-dossier-ink/30">→</span>
                <StatusPill status={t.to_status} />
                <span className="font-mono text-dossier-ink/40">{t.actor}</span>
                <RelativeTime at={t.at} />
              </div>
              {t.reason && <p className="mt-0.5 text-xs italic text-dossier-ink/40">&ldquo;{t.reason}&rdquo;</p>}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Tab bar
// ---------------------------------------------------------------------------

type Tab = "overview" | "investigation" | "response" | "history"

const TABS: { id: Tab; label: string }[] = [
  { id: "overview",      label: "Overview"      },
  { id: "investigation", label: "Investigation" },
  { id: "response",      label: "Response"      },
  { id: "history",       label: "History"       },
]

function TabBar({
  active,
  onChange,
  counts,
}: {
  active: Tab
  onChange: (t: Tab) => void
  counts: Partial<Record<Tab, number>>
}) {
  return (
    <div className="flex border-b border-dossier-paperEdge">
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`relative px-5 py-3 font-case text-[11px] font-semibold uppercase tracking-widest transition-colors ${
            active === id
              ? "text-dossier-evidenceTape"
              : "text-dossier-ink/35 hover:text-dossier-ink/70"
          }`}
        >
          {label}
          {counts[id] != null && (
            <span className={`ml-1.5 font-mono text-[9px] ${active === id ? "text-dossier-evidenceTape/60" : "text-dossier-ink/20"}`}>
              {counts[id]}
            </span>
          )}
          {active === id && (
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-dossier-evidenceTape" style={{ boxShadow: "0 0 8px rgba(0,212,255,0.6)" }} />
          )}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-28 rounded-lg border border-dossier-paperEdge bg-dossier-paper" />
      <div className="h-24 rounded-lg border border-dossier-paperEdge bg-dossier-paper" />
      <div className="h-12 rounded-lg border border-dossier-paperEdge bg-dossier-paper" />
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-32 rounded-lg border border-dossier-paperEdge bg-dossier-paper">
            <div className="m-4 space-y-2">
              {Array.from({ length: 3 }).map((_, j) => <SkeletonRow key={j} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const fetcher = useCallback(() => getIncident(id), [id])
  const { data: incident, error, loading, refetch } = useStream({
    topics: ["incidents", "detections", "actions", "evidence"],
    fetcher,
    shouldRefetch: (e) => "incident_id" in e.data && e.data.incident_id === id,
    fallbackPollMs: 30_000,
  })

  const [activeTab, setActiveTab] = useState<Tab>("overview")
  const [proposeOpen, setProposeOpen] = useState(false)
  const [prefill, setPrefill] = useState<{ kind: ActionKind; form: Record<string, string> } | undefined>(undefined)

  const openPropose = useCallback(
    (p?: { kind: ActionKind; form: Record<string, string> }) => { setPrefill(p); setProposeOpen(true) },
    [],
  )
  const useRecommendation = useCallback((rec: RecommendedAction) => {
    const form: Record<string, string> = {}
    for (const [k, v] of Object.entries(rec.params)) form[k] = v == null ? "" : String(v)
    openPropose({ kind: rec.kind, form })
  }, [openPropose])

  const recsRefreshKey = incident ? incident.actions.map((a) => `${a.id}:${a.status}`).sort().join("|") : ""
  const isNotFound = error instanceof ApiError && error.status === 404

  if (isNotFound) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center">
        <span className="font-mono text-xs tracking-widest text-dossier-redaction/40">404 NOT FOUND</span>
        <p className="font-case text-xl font-bold uppercase tracking-wider text-dossier-ink/60">Case file not found</p>
        <Link href="/incidents" className="font-case text-[10px] uppercase tracking-widest text-dossier-evidenceTape underline underline-offset-2 hover:text-dossier-ink transition-colors">
          ← Back to incidents
        </Link>
      </div>
    )
  }

  return (
    <div>
      {/* Back */}
      <Link
        href="/incidents"
        className="mb-5 inline-flex items-center gap-1.5 font-case text-[10px] uppercase tracking-widest text-dossier-ink/35 transition-colors hover:text-dossier-evidenceTape"
      >
        ← Incidents
      </Link>

      {/* Error banners */}
      {error && !loading && incident && (
        <div className="mb-4 flex items-center gap-2 rounded border border-cyber-orange/30 bg-cyber-orange/5 px-3 py-2 font-mono text-[10px] text-cyber-orange">
          <span>⚠</span><span>Refresh failed — {error.message}</span>
          <button onClick={refetch} className="ml-auto underline hover:text-dossier-evidenceTape">Retry</button>
        </div>
      )}
      {error && !incident && !loading && <ErrorState error={error} onRetry={refetch} />}

      {loading && !incident ? (
        <DetailSkeleton />
      ) : incident ? (
        <div className="space-y-4">

          {/* ── Incident header card ── */}
          <div className="overflow-hidden rounded-xl border border-dossier-paperEdge bg-dossier-paper shadow-dossier">
            <div className="px-5 py-5">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-mono text-[9px] tracking-widest text-dossier-evidenceTape/40">
                  INC-{incident.id.slice(-8).toUpperCase()}
                </span>
                <span className="font-mono text-[9px] text-dossier-ink/20">·</span>
                <span className="font-case text-[9px] uppercase tracking-widest text-dossier-ink/25">
                  {incident.kind.replace(/_/g, " ")}
                </span>
              </div>
              <h1 className="mb-3 text-lg font-semibold leading-snug text-dossier-ink">
                {incident.title}
              </h1>
              <div className="flex flex-wrap items-center gap-2.5">
                <SeverityBadge severity={incident.severity} />
                <StatusPill status={incident.status} />
                <TransitionMenu incidentId={incident.id} currentStatus={incident.status} onTransitioned={refetch} />
                <span className="flex items-center gap-1.5 font-mono text-xs text-dossier-ink/40">
                  <JargonTerm slug="confidence">confidence</JargonTerm>
                  <ConfidenceBar value={incident.confidence} />
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-5 border-t border-dossier-paperEdge bg-dossier-stamp/60 px-5 py-2.5 font-mono text-[10px] text-dossier-ink/30">
              <span>opened · <RelativeTime at={incident.opened_at} /></span>
              <span>updated · <RelativeTime at={incident.updated_at} /></span>
              {incident.closed_at && <span>closed · <RelativeTime at={incident.closed_at} /></span>}
              <span className="ml-auto">
                <JargonTerm slug="correlator">{incident.correlator_rule}@{incident.correlator_version}</JargonTerm>
              </span>
            </div>
          </div>

          {/* ── Summary card — always visible ── */}
          <div className="rounded-xl border border-dossier-evidenceTape/20 bg-dossier-paper p-5"
            style={{ boxShadow: "inset 0 0 40px rgba(0,212,255,0.02)" }}>
            <div className="mb-2 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-dossier-evidenceTape/60" />
              <p className="font-case text-[10px] font-semibold uppercase tracking-widest text-dossier-evidenceTape">
                What happened
              </p>
            </div>
            <p className="max-w-prose text-sm leading-relaxed text-dossier-ink/80">
              {incident.rationale}
            </p>
          </div>

          {/* ── Tabs ── */}
          <div className="rounded-xl border border-dossier-paperEdge bg-dossier-paper shadow-dossier overflow-hidden">
            <TabBar
              active={activeTab}
              onChange={setActiveTab}
              counts={{
                investigation: incident.timeline.length + incident.detections.length,
                response: incident.actions.length,
                history: incident.transitions.length,
              }}
            />

            <div className="p-5">
              {/* Overview tab */}
              {activeTab === "overview" && (
                <div className="space-y-5">
                  <div data-tour="kill-chain-panel">
                    <AttackKillChainPanel attack={incident.attack} />
                  </div>
                  <IncidentTimelineViz events={incident.timeline} detections={incident.detections} />
                  <EntityGraphPanel entities={incident.entities} events={incident.timeline} />
                  {incident.entities.length > 0 && (
                    <Panel title="Key Entities" count={incident.entities.length}>
                      <div className="flex flex-wrap gap-2">
                        {incident.entities.map((e) => (
                          <EntityChip key={e.id} id={e.id} kind={e.kind as EntityKind} naturalKey={e.natural_key} role={e.role_in_incident} />
                        ))}
                      </div>
                    </Panel>
                  )}
                </div>
              )}

              {/* Investigation tab */}
              {activeTab === "investigation" && (
                <div className="space-y-4">
                  <TimelinePanel events={incident.timeline} entities={incident.entities} />
                  <DetectionsPanel detections={incident.detections} />
                </div>
              )}

              {/* Response tab */}
              {activeTab === "response" && (
                <div className="space-y-4">
                  <RecommendedActionsPanel
                    incidentId={incident.id}
                    refreshKey={recsRefreshKey}
                    onUseRecommendation={useRecommendation}
                  />
                  <div data-tour="actions-panel">
                    <ActionsPanel
                      incidentId={incident.id}
                      actions={incident.actions}
                      onMutated={refetch}
                      onPropose={() => openPropose()}
                    />
                  </div>
                  <EvidenceRequestsPanel incidentId={incident.id} />
                  <EntitiesPanel entities={incident.entities} />
                </div>
              )}

              {/* History tab */}
              {activeTab === "history" && (
                <div className="space-y-4">
                  <TransitionsPanel transitions={incident.transitions} />
                  <NotesPanel incidentId={incident.id} notes={incident.notes} onNoteCreated={refetch} />
                </div>
              )}
            </div>
          </div>

        </div>
      ) : null}

      <ProposeActionModal
        open={proposeOpen}
        incidentId={id}
        onClose={() => setProposeOpen(false)}
        onProposed={() => { setProposeOpen(false); refetch() }}
        prefill={prefill}
      />
    </div>
  )
}
