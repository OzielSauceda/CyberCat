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
  "new",
  "triaged",
  "investigating",
  "contained",
  "resolved",
  "closed",
]

const ALL_SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"]

const severityBorderLeft: Record<Severity, string> = {
  info: "border-l-zinc-600",
  low: "border-l-sky-700",
  medium: "border-l-amber-600",
  high: "border-l-orange-600",
  critical: "border-l-red-600",
}

function IncidentCard({ incident }: { incident: IncidentSummary }) {
  return (
    <Link href={`/incidents/${incident.id}`} className="block group">
      <article
        className={`rounded-lg border border-zinc-800 border-l-4 bg-zinc-900 p-4 transition-colors group-hover:border-zinc-700 group-hover:bg-zinc-800/60 ${severityBorderLeft[incident.severity]}`}
      >
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <SeverityBadge severity={incident.severity} />
          <StatusPill status={incident.status} />
          <span className="ml-auto text-xs text-zinc-500">
            <RelativeTime at={incident.opened_at} />
          </span>
        </div>

        <h2 className="mb-2 line-clamp-2 text-sm font-medium text-zinc-100 group-hover:text-white">
          {incident.title}
        </h2>

        {(incident.primary_user || incident.primary_host) && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {incident.primary_user && (
              <EntityChip kind="user" naturalKey={incident.primary_user} />
            )}
            {incident.primary_host && (
              <EntityChip kind="host" naturalKey={incident.primary_host} />
            )}
          </div>
        )}

        <div className="flex items-center gap-4 text-xs text-zinc-500">
          <span title="Events">{incident.event_count} events</span>
          <span title="Detections">{incident.detection_count} detections</span>
          <span title="Entities">{incident.entity_count} entities</span>
          <span className="ml-auto font-mono text-zinc-600">
            {incident.kind.replace(/_/g, " ")}
          </span>
        </div>
      </article>
    </Link>
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
    () =>
      listIncidents({
        status: statusStr || undefined,
        severity_gte: severityGte || undefined,
        limit: 50,
      }),
    [statusStr, severityGte],
  )

  const { data, error, loading, refetch } = useStream({
    topics: ["incidents"],
    fetcher,
    shouldRefetch: (e) => e.type.startsWith("incident."),
  })

  // Keep pagination cursor in sync with polled first page
  useEffect(() => {
    if (data) setNextCursor(data.next_cursor)
  }, [data])

  // Reset extra pages when filters change
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

  const toggleStatus = (s: IncidentStatus) => {
    setStatusFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    )
  }

  const clearFilters = () => {
    setStatusFilter([])
    setSeverityGte("")
  }

  const hasFilters = statusFilter.length > 0 || severityGte !== ""
  const allItems = [...(data?.items ?? []), ...extraItems]

  return (
    <div>
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Incidents</h1>
          {data && (
            <p className="mt-0.5 text-sm text-zinc-500">
              {data.items.length + extraItems.length} loaded
              {hasFilters && " (filtered)"}
            </p>
          )}
        </div>
        {error instanceof ApiError && (
          <span className="text-xs text-amber-400">Backend unreachable — showing cached data</span>
        )}
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        {/* Status filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Status:</span>
          <div className="flex flex-wrap gap-1">
            {ALL_STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => toggleStatus(s)}
                className={`rounded-full border px-2.5 py-0.5 text-xs capitalize transition-colors ${
                  statusFilter.includes(s)
                    ? "border-indigo-700 bg-indigo-950 text-indigo-300"
                    : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Severity filter */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Min severity:</span>
          <select
            value={severityGte}
            onChange={(e) => setSeverityGte(e.target.value as Severity | "")}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300 focus:border-indigo-600 focus:outline-none"
          >
            <option value="">Any</option>
            {ALL_SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="ml-auto text-xs text-zinc-500 hover:text-zinc-300 underline underline-offset-2 transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Error banner (non-blocking if we have cached data) */}
      {error && !data && (
        <div className="mb-6">
          <ErrorState error={error} onRetry={refetch} />
        </div>
      )}
      {error && data && (
        <div className="mb-4 flex items-center gap-2 rounded border border-amber-900 bg-amber-950/30 px-3 py-2 text-xs text-amber-400">
          <span className="font-bold">!</span>
          <span>Last refresh failed — {error.message}. Showing cached data.</span>
          <button onClick={refetch} className="ml-auto underline hover:text-amber-300">
            Retry
          </button>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : allItems.length === 0 ? (
        <EmptyState
          title="No incidents yet"
          hint={
            hasFilters
              ? "No incidents match the current filters."
              : "Seed one via POST /v1/events/raw — see docs/runbook.md."
          }
          action={
            hasFilters ? (
              <button
                onClick={clearFilters}
                className="text-xs text-indigo-400 hover:text-indigo-300 underline"
              >
                Clear filters
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {allItems.map((inc) => (
              <IncidentCard key={inc.id} incident={inc} />
            ))}
          </div>

          {/* Load more */}
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
                className="rounded border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50 transition-colors"
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
