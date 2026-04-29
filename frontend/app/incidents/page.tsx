"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { EmptyState } from "../components/EmptyState"
import { EntityChip } from "../components/EntityChip"
import { ErrorState } from "../components/ErrorState"
import { RelativeTime } from "../components/RelativeTime"
import { SeverityBadge } from "../components/SeverityBadge"
import { SkeletonCard } from "../components/Skeleton"
import { StatusPill } from "../components/StatusPill"
import {
  ApiError,
  listIncidents,
  type IncidentSummary,
  type IncidentStatus,
  type Severity,
} from "../lib/api"
import { useStream } from "../lib/useStream"

const ALL_STATUSES: IncidentStatus[] = [
  "new", "triaged", "investigating", "contained", "resolved", "closed",
]

const ALL_SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"]

const severityLeftBorder: Record<Severity, string> = {
  critical: "border-l-dossier-redaction",
  high:     "border-l-cyber-orange",
  medium:   "border-l-cyber-yellow",
  low:      "border-l-sky-500",
  info:     "border-l-dossier-paperEdge",
}


function IncidentCard({
  incident,
  tourAttr,
  idx,
}: {
  incident: IncidentSummary
  tourAttr?: string
  idx?: number
}) {
  return (
    <Link
      href={`/incidents/${incident.id}`}
      className="block group"
      style={{
        animation: "card-enter 0.45s ease both",
        animationDelay: `${Math.min((idx ?? 0) * 50, 350)}ms`,
      }}
    >
      <article
        data-tour={tourAttr}
        className={`relative rounded-lg border border-dossier-paperEdge border-l-2 bg-dossier-paper transition-all duration-150 group-hover:bg-dossier-paperEdge/50 group-hover:border-dossier-evidenceTape/20 ${severityLeftBorder[incident.severity]}`}
        style={{ boxShadow: "0 2px 12px rgba(0,0,0,0.5)" }}
      >
        <div className="px-4 pt-3.5 pb-3">
          {/* Title row */}
          <h2 className="text-sm font-semibold leading-snug text-dossier-ink group-hover:text-dossier-evidenceTape transition-colors line-clamp-2 mb-2.5">
            {incident.title}
          </h2>

          {/* Meta row: severity + status + time */}
          <div className="flex flex-wrap items-center gap-2 mb-2.5">
            <SeverityBadge severity={incident.severity} />
            <StatusPill status={incident.status} />
            <span className="ml-auto font-mono text-[10px] text-dossier-ink/30">
              <RelativeTime at={incident.opened_at} />
            </span>
          </div>

          {/* Entity chips */}
          {(incident.primary_user || incident.primary_host) && (
            <div className="mb-2.5 flex flex-wrap gap-1.5">
              {incident.primary_user && (
                <EntityChip kind="user" naturalKey={incident.primary_user} />
              )}
              {incident.primary_host && (
                <EntityChip kind="host" naturalKey={incident.primary_host} />
              )}
            </div>
          )}
        </div>

        {/* Evidence strip */}
        <div className="flex items-center gap-4 border-t border-dossier-paperEdge px-4 py-2 font-mono text-[10px] text-dossier-ink/30">
          <span>{incident.event_count} events</span>
          <span>{incident.detection_count} detections</span>
          <span>{incident.entity_count} entities</span>
          <span className="ml-auto text-dossier-evidenceTape/25">
            #{incident.id.slice(-6).toUpperCase()}
          </span>
        </div>
      </article>
    </Link>
  )
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded border px-2.5 py-0.5 font-case text-[10px] font-semibold uppercase tracking-widest transition-colors ${
        active
          ? "border-dossier-evidenceTape/60 bg-dossier-evidenceTape/10 text-dossier-evidenceTape"
          : "border-dossier-paperEdge bg-dossier-paper text-dossier-ink/40 hover:border-dossier-evidenceTape/30 hover:text-dossier-ink/70"
      }`}
    >
      {children}
    </button>
  )
}

export default function IncidentsPage() {
  const [statusFilter, setStatusFilter] = useState<IncidentStatus[]>([])
  const [severityGte, setSeverityGte] = useState<Severity | "">("")
  const [extraItems, setExtraItems] = useState<IncidentSummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState<Error>()

  const statusStr = statusFilter.join(",")

  const fetcher = useCallback(
    () => listIncidents({ status: statusStr || undefined, severity_gte: severityGte || undefined, limit: 50 }),
    [statusStr, severityGte],
  )

  const { data, error, loading, refetch } = useStream({
    topics: ["incidents"],
    fetcher,
    shouldRefetch: (e) => e.type.startsWith("incident."),
  })

  useEffect(() => { if (data) setNextCursor(data.next_cursor) }, [data])
  useEffect(() => {
    setExtraItems([])
    setNextCursor(null)
    setLoadMoreError(undefined)
  }, [statusStr, severityGte])

  const handleLoadMore = async () => {
    if (!nextCursor) return
    setLoadingMore(true)
    setLoadMoreError(undefined)
    try {
      const page = await listIncidents({
        status: statusStr || undefined,
        severity_gte: severityGte || undefined,
        limit: 50,
        cursor: nextCursor,
      })
      setExtraItems((prev) => [...prev, ...page.items])
      setNextCursor(page.next_cursor)
    } catch (e) {
      setLoadMoreError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      setLoadingMore(false)
    }
  }

  const toggleStatus = (s: IncidentStatus) =>
    setStatusFilter((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s])

  const clearFilters = () => { setStatusFilter([]); setSeverityGte("") }

  const hasFilters = statusFilter.length > 0 || severityGte !== ""
  const allItems = [...(data?.items ?? []), ...extraItems]

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="font-case text-[9px] uppercase tracking-[0.35em] text-dossier-evidenceTape/50 mb-0.5">
            Active Investigations
          </p>
          <h1 className="font-case text-2xl font-bold uppercase tracking-wider text-dossier-ink">
            Incidents
          </h1>
          {data && (
            <p className="mt-0.5 font-mono text-[10px] text-dossier-ink/30">
              {allItems.length} case{allItems.length !== 1 ? "s" : ""}
              {hasFilters ? " (filtered)" : ""}
            </p>
          )}
        </div>
        {error instanceof ApiError && (
          <span className="font-mono text-[10px] text-cyber-orange/80">
            ⚠ backend unreachable
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-case text-[9px] uppercase tracking-[0.25em] text-dossier-ink/30 pr-1">
            Status
          </span>
          {ALL_STATUSES.map((s) => (
            <FilterButton key={s} active={statusFilter.includes(s)} onClick={() => toggleStatus(s)}>
              {s}
            </FilterButton>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <span className="font-case text-[9px] uppercase tracking-[0.25em] text-dossier-ink/30">
            Min sev
          </span>
          <select
            value={severityGte}
            onChange={(e) => setSeverityGte(e.target.value as Severity | "")}
            className="rounded border border-dossier-paperEdge bg-dossier-paper px-2 py-0.5 font-case text-[10px] uppercase tracking-wider text-dossier-ink/60 focus:border-dossier-evidenceTape focus:outline-none"
          >
            <option value="">Any</option>
            {ALL_SEVERITIES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="ml-auto font-case text-[10px] uppercase tracking-widest text-dossier-redaction/60 hover:text-dossier-redaction underline underline-offset-2 transition-colors"
          >
            Clear ×
          </button>
        )}
      </div>

      {/* Error states */}
      {error && !data && <div className="mb-6"><ErrorState error={error} onRetry={refetch} /></div>}
      {error && data && (
        <div className="mb-4 flex items-center gap-2 rounded border border-cyber-orange/30 bg-cyber-orange/5 px-3 py-2 font-mono text-[10px] text-cyber-orange">
          <span>⚠</span>
          <span>Last refresh failed — {error.message}</span>
          <button onClick={refetch} className="ml-auto underline hover:text-dossier-evidenceTape">Retry</button>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : allItems.length === 0 ? (
        <EmptyState
          title={hasFilters ? "No cases match your filters" : "Board is clear"}
          hint={
            hasFilters
              ? "Try loosening the filters or clearing them to see everything."
              : "Nothing here yet. Load the demo data to explore a sample case, or send events to the backend to start monitoring."
          }
          action={
            hasFilters ? (
              <button
                onClick={clearFilters}
                className="font-case text-[10px] uppercase tracking-widest text-dossier-evidenceTape underline underline-offset-2 hover:text-dossier-ink transition-colors"
              >
                Clear filters
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {allItems.map((inc, idx) => (
              <IncidentCard
                key={inc.id}
                incident={inc}
                idx={idx}
                tourAttr={idx === 0 ? "incident-card-first" : undefined}
              />
            ))}
          </div>

          {nextCursor && (
            <div className="mt-8 flex justify-center">
              {loadMoreError && (
                <div className="mb-3 w-full max-w-sm">
                  <ErrorState error={loadMoreError} onRetry={handleLoadMore} />
                </div>
              )}
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="rounded border border-dossier-paperEdge bg-dossier-paper px-5 py-2 font-case text-[10px] uppercase tracking-widest text-dossier-ink/50 hover:border-dossier-evidenceTape/30 hover:text-dossier-ink transition-colors disabled:opacity-40"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
