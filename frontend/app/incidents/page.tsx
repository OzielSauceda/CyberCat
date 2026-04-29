"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { EmptyState } from "../components/EmptyState"
import { ErrorState } from "../components/ErrorState"
import { RelativeTime } from "../components/RelativeTime"
import { SkeletonCard } from "../components/Skeleton"
import {
  ApiError,
  listIncidents,
  type IncidentSummary,
  type IncidentStatus,
  type Severity,
} from "../lib/api"
import { useStream } from "../lib/useStream"

const SEV_COLOR: Record<Severity, string> = {
  critical: "#ff2d55",
  high:     "#ff6b35",
  medium:   "#fbbf24",
  low:      "#38bdf8",
  info:     "#6b7280",
}

const SEV_LABEL: Record<Severity, string> = {
  critical: "CRIT",
  high:     "HIGH",
  medium:   "MED",
  low:      "LOW",
  info:     "INFO",
}

const STATUS_COLOR: Record<string, string> = {
  new:           "#9ca3af",
  triaged:       "#60a5fa",
  investigating: "#fb923c",
  contained:     "#fbbf24",
  resolved:      "#34d399",
  closed:        "#4b5563",
  reopened:      "#c084fc",
}

const ALL_STATUSES: IncidentStatus[] = [
  "new", "triaged", "investigating", "contained", "resolved", "closed",
]

const ALL_SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"]

// ── Filter chip ───────────────────────────────────────────────────────────────

function Chip({
  label, active, color, onClick,
}: {
  label: string; active: boolean; color?: string; onClick: () => void
}) {
  const c = color ?? "#cdd6df"
  return (
    <button
      onClick={onClick}
      className="px-2.5 py-1 font-case text-[11px] font-semibold uppercase tracking-wide border transition-all duration-150"
      style={{
        borderColor: active ? `${c}55` : "#0c1b2e",
        background:  active ? `${c}12` : "transparent",
        color:       active ? c : "#cdd6df28",
      }}
    >
      {label}
    </button>
  )
}

// ── Incident row ──────────────────────────────────────────────────────────────

function IncidentRow({
  incident, tourAttr, idx,
}: {
  incident: IncidentSummary; tourAttr?: string; idx?: number
}) {
  const sevColor    = SEV_COLOR[incident.severity]
  const statusColor = STATUS_COLOR[incident.status] ?? "#9ca3af"

  const entityText =
    incident.primary_user && incident.primary_host
      ? `${incident.primary_user} @ ${incident.primary_host}`
      : incident.primary_user ?? incident.primary_host ?? null

  return (
    <Link
      href={`/incidents/${incident.id}`}
      className="block group"
      style={{
        animation: "card-enter 0.3s ease both",
        animationDelay: `${Math.min((idx ?? 0) * 30, 200)}ms`,
      }}
    >
      <article
        data-tour={tourAttr}
        className="flex items-stretch border border-dossier-paperEdge bg-dossier-stamp overflow-hidden transition-all duration-150 group-hover:border-dossier-evidenceTape/20 group-hover:bg-dossier-paperEdge/20"
      >
        {/* Severity stripe */}
        <div
          className="w-[3px] shrink-0 transition-all duration-150 group-hover:w-1"
          style={{ background: sevColor, boxShadow: `0 0 6px ${sevColor}55` }}
        />

        {/* Row content */}
        <div className="flex flex-1 items-center gap-4 px-4 py-3 min-w-0">
          {/* Severity label */}
          <span
            className="shrink-0 font-case text-xs font-bold uppercase tracking-wide w-9 leading-none"
            style={{ color: sevColor }}
          >
            {SEV_LABEL[incident.severity]}
          </span>

          {/* Title + entity */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-dossier-ink/85 group-hover:text-dossier-ink transition-colors truncate">
              {incident.title}
            </p>
            {entityText && (
              <p className="mt-0.5 font-mono text-xs text-dossier-ink/30 truncate">
                {entityText}
              </p>
            )}
          </div>

          {/* Status */}
          <span
            className="shrink-0 font-case text-xs font-semibold uppercase tracking-wide hidden sm:block"
            style={{ color: statusColor }}
          >
            {incident.status}
          </span>

          {/* Event count */}
          <span className="shrink-0 font-mono text-xs text-dossier-ink/20 hidden md:block">
            {incident.event_count} ev
          </span>

          {/* Time */}
          <span className="shrink-0 font-mono text-xs text-dossier-ink/30 whitespace-nowrap">
            <RelativeTime at={incident.opened_at} />
          </span>

          {/* ID + arrow */}
          <span className="shrink-0 font-mono text-xs text-dossier-evidenceTape/20 group-hover:text-dossier-evidenceTape/50 transition-colors hidden lg:flex items-center gap-1.5">
            #{incident.id.slice(-6).toUpperCase()}
            <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </span>
        </div>
      </article>
    </Link>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IncidentsPage() {
  const [statusFilter,  setStatusFilter]  = useState<IncidentStatus[]>([])
  const [severityGte,   setSeverityGte]   = useState<Severity | "">("")
  const [extraItems,    setExtraItems]    = useState<IncidentSummary[]>([])
  const [nextCursor,    setNextCursor]    = useState<string | null>(null)
  const [loadingMore,   setLoadingMore]   = useState(false)
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
    setStatusFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    )

  const clearFilters = () => { setStatusFilter([]); setSeverityGte("") }

  const hasFilters = statusFilter.length > 0 || severityGte !== ""
  const allItems   = [...(data?.items ?? []), ...extraItems]

  return (
    <div className="space-y-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-case text-2xl font-bold uppercase tracking-wider text-dossier-ink">
            Incidents
          </h1>
          <p className="mt-0.5 font-mono text-xs text-dossier-ink/30">
            {data
              ? `${allItems.length} case${allItems.length !== 1 ? "s" : ""}${hasFilters ? " · filtered" : ""}`
              : "Loading…"}
          </p>
        </div>
        {error instanceof ApiError && (
          <span className="font-mono text-xs text-cyber-orange/70">⚠ backend unreachable</span>
        )}
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">status</span>
        {ALL_STATUSES.map((s) => (
          <Chip
            key={s}
            label={s}
            active={statusFilter.includes(s)}
            color={STATUS_COLOR[s]}
            onClick={() => toggleStatus(s)}
          />
        ))}
        <div className="w-px h-4 bg-dossier-paperEdge mx-2" />
        <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">min sev</span>
        {ALL_SEVERITIES.map((s) => (
          <Chip
            key={s}
            label={SEV_LABEL[s]}
            active={severityGte === s}
            color={SEV_COLOR[s]}
            onClick={() => setSeverityGte((prev) => (prev === s ? "" : s))}
          />
        ))}
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="ml-auto font-mono text-[11px] uppercase tracking-widest text-dossier-redaction/40 hover:text-dossier-redaction transition-colors"
          >
            × clear
          </button>
        )}
      </div>

      {/* ── Errors ───────────────────────────────────────────────────────── */}
      {error && !data && <ErrorState error={error} onRetry={refetch} />}
      {error && data && (
        <div className="flex items-center gap-2 border border-cyber-orange/20 bg-cyber-orange/5 px-3 py-2 font-mono text-xs text-cyber-orange">
          <span>⚠ Last refresh failed — {error.message}</span>
          <button onClick={refetch} className="ml-auto underline hover:text-dossier-evidenceTape">Retry</button>
        </div>
      )}

      {/* ── Content ──────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="space-y-1.5">
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
                className="font-case text-xs uppercase tracking-widest text-dossier-evidenceTape underline underline-offset-2 hover:text-dossier-ink transition-colors"
              >
                Clear filters
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="space-y-1">
            {allItems.map((inc, idx) => (
              <IncidentRow
                key={inc.id}
                incident={inc}
                idx={idx}
                tourAttr={idx === 0 ? "incident-card-first" : undefined}
              />
            ))}
          </div>

          {nextCursor && (
            <div className="mt-6 flex flex-col items-center gap-3">
              {loadMoreError && (
                <div className="w-full max-w-sm">
                  <ErrorState error={loadMoreError} onRetry={handleLoadMore} />
                </div>
              )}
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="border border-dossier-paperEdge bg-dossier-stamp px-5 py-2 font-case text-xs uppercase tracking-widest text-dossier-ink/40 hover:border-dossier-evidenceTape/25 hover:text-dossier-ink/70 transition-all disabled:opacity-30"
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
