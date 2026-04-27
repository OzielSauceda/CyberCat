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
  type AttackRef,
  type EntityKind,
  type EntityRef,
  type IncidentDetail,
  type TimelineEvent,
} from "../../lib/api"
import { useAttackEntry } from "../../lib/attackCatalog"
import { useStream } from "../../lib/useStream"
import { EvidenceRequestsPanel } from "../../components/EvidenceRequestsPanel"
import { ActionsPanel } from "./ActionsPanel"
import { AttackKillChainPanel } from "./AttackKillChainPanel"
import { EntityGraphPanel } from "./EntityGraphPanel"
import { IncidentTimelineViz } from "./IncidentTimelineViz"
import { NotesPanel } from "./NotesPanel"

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
        .filter(Boolean)
        .join(" ")
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
        .filter(Boolean)
        .join(" ")
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
        if (!groups.has(entity.id)) {
          groups.set(entity.id, { entity, events: [] })
          order.push(entity.id)
        }
        groups.get(entity.id)!.events.push(event)
        assigned = true
        break
      }
    }
    if (!assigned) {
      if (!groups.has("__other__")) {
        groups.set("__other__", { entity: null, events: [] })
        order.push("__other__")
      }
      groups.get("__other__")!.events.push(event)
    }
  }

  return order.map((k) => groups.get(k)!)
}

const roleStyles: Record<string, string> = {
  trigger: "text-red-300 bg-red-950 border-red-900",
  supporting: "text-zinc-400 bg-zinc-800 border-zinc-700",
  context: "text-zinc-500 bg-zinc-900 border-zinc-800",
}

// ---------------------------------------------------------------------------
// Sub-panels
// ---------------------------------------------------------------------------

function TimelinePanel({
  events,
  entities,
}: {
  events: TimelineEvent[]
  entities: EntityRef[]
}) {
  const [byEntity, setByEntity] = useState(true)

  const renderEvent = (ev: TimelineEvent, showEntityChips = true) => {
    const summary = getEventSummary(ev)
    const linkedEntities = entities.filter((e) => ev.entity_ids.includes(e.id))

    return (
      <div
        key={ev.id}
        className="group flex flex-col gap-1 border-b border-zinc-800 py-2.5 last:border-0"
      >
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-zinc-500">
            {new Date(ev.occurred_at).toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </span>
          <span className="font-mono font-medium text-zinc-200">{ev.kind}</span>
          <span className="rounded border border-zinc-800 bg-zinc-950 px-1 py-0.5 text-zinc-500">
            {ev.source}
          </span>
          <span
            className={`rounded border px-1.5 py-0.5 text-xs font-medium ${roleStyles[ev.role_in_incident] ?? roleStyles.context}`}
          >
            {ev.role_in_incident}
          </span>
          {summary && (
            <span className="font-mono text-zinc-300 ml-auto text-right">{summary}</span>
          )}
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
    <Panel title="Timeline" count={events.length}>
      {/* View toggle */}
      <div className="mb-3 flex gap-1">
        {[
          { id: true, label: "By entity" },
          { id: false, label: "Chronological" },
        ].map(({ id, label }) => (
          <button
            key={String(id)}
            onClick={() => setByEntity(id)}
            className={`rounded px-2.5 py-1 text-xs transition-colors ${
              byEntity === id
                ? "bg-zinc-700 text-zinc-100"
                : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {events.length === 0 ? (
        <EmptyState title="No events linked" />
      ) : byEntity ? (
        groupEventsByEntity(events, entities).map(({ entity, events: evs }) => (
          <div key={entity?.id ?? "__other__"} className="mb-4 last:mb-0">
            <div className="mb-1.5 flex items-center gap-2">
              {entity ? (
                <EntityChip
                  id={entity.id}
                  kind={entity.kind as EntityKind}
                  naturalKey={entity.natural_key}
                  role={entity.role_in_incident}
                />
              ) : (
                <span className="text-xs text-zinc-600">Other</span>
              )}
              <span className="text-xs text-zinc-600">{evs.length} events</span>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3">
              {evs.map((ev) => renderEvent(ev, false))}
            </div>
          </div>
        ))
      ) : (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3">
          {events.map((ev) => renderEvent(ev))}
        </div>
      )}
    </Panel>
  )
}

function DetectionsPanel({ detections }: { detections: IncidentDetail["detections"] }) {
  return (
    <Panel title="Detections" count={detections.length}>
      {detections.length === 0 ? (
        <EmptyState title="No detections" />
      ) : (
        <div className="space-y-4">
          {detections.map((d) => (
            <div
              key={d.id}
              className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
            >
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span className="font-mono text-sm font-medium text-zinc-100">{d.rule_id}</span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-xs font-mono ${
                    d.rule_source === "sigma"
                      ? "border-violet-800 bg-violet-950 text-violet-300"
                      : "border-blue-800 bg-blue-950 text-blue-300"
                  }`}
                >
                  {d.rule_source}
                </span>
                <span className="text-xs text-zinc-500">v{d.rule_version}</span>
              </div>
              <div className="flex flex-wrap items-center gap-3 mb-2 text-xs text-zinc-400">
                <SeverityBadge severity={d.severity_hint} />
                <span className="flex items-center gap-1">
                  Confidence <ConfidenceBar value={d.confidence_hint} />
                </span>
              </div>
              {d.attack_tags.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
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
    <Panel title="Entities" count={entities.length}>
      {entities.length === 0 ? (
        <EmptyState title="No entities linked" />
      ) : (
        <div className="space-y-3">
          {(Object.entries(grouped) as [EntityKind, EntityRef[]][]).map(([kind, ents]) => (
            <div key={kind}>
              <p className="mb-1.5 text-xs uppercase tracking-wider text-zinc-600">{kind}</p>
              <div className="space-y-2">
                {ents.map((e) => (
                  <div
                    key={e.id}
                    className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2 mb-1.5">
                      <EntityChip id={e.id} kind={kind} naturalKey={e.natural_key} />
                      <span className="text-xs text-zinc-500">{e.role_in_incident}</span>
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
  return (
    <AttackTag
      technique={technique}
      subtechnique={subtechnique}
      source={source}
      name={entry?.name}
    />
  )
}


function TransitionsPanel({ transitions }: { transitions: IncidentDetail["transitions"] }) {
  return (
    <Panel title="Status history" count={transitions.length}>
      {transitions.length === 0 ? (
        <EmptyState title="No transitions recorded" />
      ) : (
        <ol className="relative border-l border-zinc-800 ml-2 space-y-4 pl-4">
          {transitions.map((t, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[1.4rem] mt-0.5 flex h-3 w-3 items-center justify-center">
                <span className="h-2 w-2 rounded-full bg-zinc-600" />
              </span>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {t.from_status ? (
                  <StatusPill status={t.from_status} />
                ) : (
                  <span className="text-zinc-600">—</span>
                )}
                <span className="text-zinc-600">→</span>
                <StatusPill status={t.to_status} />
                <span className="text-zinc-500">{t.actor}</span>
                <RelativeTime at={t.at} />
              </div>
              {t.reason && (
                <p className="mt-0.5 text-xs text-zinc-500 italic">"{t.reason}"</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}


// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="space-y-3">
        <div className="h-7 w-2/3 rounded bg-zinc-800" />
        <div className="flex gap-2">
          <div className="h-5 w-12 rounded bg-zinc-800" />
          <div className="h-5 w-24 rounded-full bg-zinc-800" />
          <div className="h-5 w-32 rounded bg-zinc-800" />
        </div>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="mb-2 h-3 w-32 rounded bg-zinc-800" />
        <div className="space-y-2">
          <div className="h-4 w-full rounded bg-zinc-800" />
          <div className="h-4 w-5/6 rounded bg-zinc-800" />
          <div className="h-4 w-4/6 rounded bg-zinc-800" />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
            <div className="mb-3 h-3 w-24 rounded bg-zinc-800" />
            {Array.from({ length: 3 }).map((_, j) => (
              <SkeletonRow key={j} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)

  const fetcher = useCallback(() => getIncident(id), [id])
  const { data: incident, error, loading, refetch } = useStream({
    topics: ["incidents", "detections", "actions", "evidence"],
    fetcher,
    shouldRefetch: (e) => "incident_id" in e.data && e.data.incident_id === id,
    fallbackPollMs: 30_000,
  })

  const isNotFound = error instanceof ApiError && error.status === 404

  if (isNotFound) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center">
        <span className="text-4xl text-zinc-700">404</span>
        <p className="text-zinc-300">Incident not found.</p>
        <Link
          href="/incidents"
          className="text-sm text-indigo-400 hover:text-indigo-300 underline underline-offset-2"
        >
          ← Back to incidents
        </Link>
      </div>
    )
  }

  return (
    <div>
      {/* Back link */}
      <Link
        href="/incidents"
        className="mb-4 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        ← Incidents
      </Link>

      {/* Non-blocking error banner */}
      {error && !loading && incident && (
        <div className="mb-4 flex items-center gap-2 rounded border border-amber-900 bg-amber-950/30 px-3 py-2 text-xs text-amber-400">
          <span className="font-bold">!</span>
          <span>Refresh failed — {error.message}</span>
          <button onClick={refetch} className="ml-auto underline hover:text-amber-300">
            Retry
          </button>
        </div>
      )}
      {error && !incident && !loading && (
        <ErrorState error={error} onRetry={refetch} />
      )}

      {loading && !incident ? (
        <DetailSkeleton />
      ) : incident ? (
        <div className="space-y-6">
          {/* ── Header ── */}
          <div>
            <h1 className="mb-3 text-xl font-semibold leading-snug text-zinc-50">
              {incident.title}
            </h1>
            <div className="flex flex-wrap items-center gap-3">
              <SeverityBadge severity={incident.severity} />
              <StatusPill status={incident.status} />
              <TransitionMenu
                incidentId={incident.id}
                currentStatus={incident.status}
                onTransitioned={refetch}
              />
              <ConfidenceBar value={incident.confidence} />
              <span className="font-mono text-xs text-zinc-500">
                {incident.kind.replace(/_/g, " ")}
              </span>
              <span className="font-mono text-xs text-zinc-600">
                {incident.correlator_rule}@{incident.correlator_version}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-4 text-xs text-zinc-500">
              <span>
                Opened <RelativeTime at={incident.opened_at} />
              </span>
              <span>
                Updated <RelativeTime at={incident.updated_at} />
              </span>
              {incident.closed_at && (
                <span>
                  Closed <RelativeTime at={incident.closed_at} />
                </span>
              )}
            </div>
          </div>

          {/* ── Rationale ── */}
          <div className="rounded-lg border border-indigo-900 bg-indigo-950/20 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-indigo-400">
              Why this is one incident
            </p>
            <p className="text-sm leading-relaxed text-zinc-200 max-w-prose">
              {incident.rationale}
            </p>
          </div>

          {/* ── ATT&CK kill chain (full-width) ── */}
          <AttackKillChainPanel attack={incident.attack} />

          {/* ── Graphical timeline (full-width) ── */}
          <IncidentTimelineViz
            events={incident.timeline}
            detections={incident.detections}
          />

          {/* ── Two-column evidence grid ── */}
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Left: timeline + detections */}
            <div className="space-y-4">
              <TimelinePanel events={incident.timeline} entities={incident.entities} />
              <DetectionsPanel detections={incident.detections} />
            </div>

            {/* Right: context + response */}
            <div className="space-y-4">
              <EntityGraphPanel entities={incident.entities} events={incident.timeline} />
              <EntitiesPanel entities={incident.entities} />
              <ActionsPanel incidentId={incident.id} actions={incident.actions} onMutated={refetch} />
              <EvidenceRequestsPanel incidentId={incident.id} />
              <TransitionsPanel transitions={incident.transitions} />
              <NotesPanel incidentId={incident.id} notes={incident.notes} onNoteCreated={refetch} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
