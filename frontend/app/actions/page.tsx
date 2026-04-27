"use client"

import { useCallback, useState } from "react"
import { ActionClassificationBadge } from "../components/ActionClassificationBadge"
import { EmptyState } from "../components/EmptyState"
import { ErrorState } from "../components/ErrorState"
import { RelativeTime } from "../components/RelativeTime"
import { SkeletonCard } from "../components/Skeleton"
import { StatusPill } from "../components/StatusPill"
import {
  listActions,
  type ActionClassification,
  type ActionKind,
  type ActionStatus,
  type ActionSummary,
} from "../lib/api"
import { useStream } from "../lib/useStream"

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACTION_KINDS: ActionKind[] = [
  "tag_incident",
  "elevate_severity",
  "flag_host_in_lab",
  "quarantine_host_lab",
  "invalidate_lab_session",
  "block_observable",
  "kill_process_lab",
  "request_evidence",
]

const CLASSIFICATION_OPTIONS: Array<ActionClassification | ""> = [
  "",
  "auto_safe",
  "suggest_only",
  "reversible",
  "disruptive",
]

const STATUS_OPTIONS: Array<ActionStatus | ""> = [
  "",
  "proposed",
  "executed",
  "failed",
  "skipped",
  "reverted",
]

type SinceKey = "1h" | "24h" | "7d" | "all"
const SINCE_LABELS: Record<SinceKey, string> = {
  "1h": "Last 1h",
  "24h": "Last 24h",
  "7d": "Last 7d",
  all: "All time",
}

function sinceIso(key: SinceKey): string | undefined {
  if (key === "1h") return new Date(Date.now() - 3_600_000).toISOString()
  if (key === "24h") return new Date(Date.now() - 86_400_000).toISOString()
  if (key === "7d") return new Date(Date.now() - 604_800_000).toISOString()
  return undefined
}

function targetFromParams(params: Record<string, unknown>): string | null {
  const v =
    params["tag"] ??
    params["natural_key"] ??
    params["to"] ??
    params["host"] ??
    params["process_id"] ??
    params["observable"]
  return v != null ? String(v) : null
}

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

function ActionRow({ action }: { action: ActionSummary }) {
  const target = targetFromParams(action.params)
  return (
    <tr className="border-b border-zinc-800 hover:bg-zinc-900/60 transition-colors">
      <td className="px-3 py-2.5">
        <ActionClassificationBadge classification={action.classification} />
      </td>
      <td className="px-3 py-2.5 font-mono text-sm text-zinc-300">{action.kind}</td>
      <td className="px-3 py-2.5">
        <StatusPill status={action.status} />
      </td>
      <td className="px-3 py-2.5 text-xs text-zinc-400">
        <span
          className={`rounded border px-1.5 py-0.5 text-xs ${
            action.proposed_by === "system"
              ? "border-zinc-700 bg-zinc-900 text-zinc-500"
              : "border-indigo-800 bg-indigo-950 text-indigo-300"
          }`}
        >
          {action.proposed_by}
        </span>
      </td>
      <td className="px-3 py-2.5 text-xs text-zinc-400">
        <RelativeTime at={action.proposed_at} />
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
        {target ?? <span className="text-zinc-600">—</span>}
      </td>
      <td className="px-3 py-2.5 text-xs">
        {action.last_log?.executed_by ? (
          <span className="text-zinc-500">{action.last_log.executed_by}</span>
        ) : (
          <span className="text-zinc-600">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-xs">
        {/* incident_id is not in ActionSummary directly — navigate via proposed_by=system hint */}
        <span className="text-zinc-600 text-xs">view on incident</span>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// ActionRowWithLink — fetches incident context from params
// ---------------------------------------------------------------------------

function ActionTable({ items }: { items: ActionSummary[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/60 text-left text-xs font-medium text-zinc-500 uppercase tracking-wide">
            <th className="px-3 py-2">Classification</th>
            <th className="px-3 py-2">Kind</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Proposed by</th>
            <th className="px-3 py-2">When</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2">Executed by</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <ActionRow key={a.id} action={a} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ActionsPage() {
  const [statusFilter, setStatusFilter] = useState<ActionStatus | "">("")
  const [classFilter, setClassFilter] = useState<ActionClassification | "">("")
  const [kindFilter, setKindFilter] = useState<ActionKind | "">("")
  const [sinceKey, setSinceKey] = useState<SinceKey>("24h")

  const fetcher = useCallback(
    () =>
      listActions({
        status: statusFilter || undefined,
        classification: classFilter || undefined,
        kind: kindFilter || undefined,
        since: sinceIso(sinceKey),
        limit: 50,
      }),
    [statusFilter, classFilter, kindFilter, sinceKey],
  )

  const { data, error, loading, refetch } = useStream({
    topics: ["actions"],
    fetcher,
    shouldRefetch: (e) => e.type.startsWith("action."),
  })

  const hasFilters =
    statusFilter !== "" || classFilter !== "" || kindFilter !== "" || sinceKey !== "24h"

  const clearFilters = () => {
    setStatusFilter("")
    setClassFilter("")
    setKindFilter("")
    setSinceKey("24h")
  }

  const allItems = data?.items ?? []

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Response Actions</h1>
          {data && (
            <p className="mt-0.5 text-sm text-zinc-500">
              {allItems.length} loaded{hasFilters && " (filtered)"}
            </p>
          )}
        </div>
        <p className="text-xs text-zinc-600">
          Execute / Revert actions on the incident detail page.
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        {/* Status */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Status:</span>
          <div className="flex flex-wrap gap-1">
            {STATUS_OPTIONS.map((s) => (
              <button
                key={s || "all"}
                onClick={() => setStatusFilter(s as ActionStatus | "")}
                className={`rounded-full border px-2.5 py-0.5 text-xs capitalize transition-colors ${
                  statusFilter === s
                    ? "border-indigo-700 bg-indigo-950 text-indigo-300"
                    : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {s || "any"}
              </button>
            ))}
          </div>
        </div>

        {/* Classification */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Class:</span>
          <div className="flex flex-wrap gap-1">
            {CLASSIFICATION_OPTIONS.map((c) => (
              <button
                key={c || "all"}
                onClick={() => setClassFilter(c as ActionClassification | "")}
                className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                  classFilter === c
                    ? "border-indigo-700 bg-indigo-950 text-indigo-300"
                    : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {c || "any"}
              </button>
            ))}
          </div>
        </div>

        {/* Kind */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Kind:</span>
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value as ActionKind | "")}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300 focus:border-indigo-600 focus:outline-none"
          >
            <option value="">any</option>
            {ACTION_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </div>

        {/* Since */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Since:</span>
          <select
            value={sinceKey}
            onChange={(e) => setSinceKey(e.target.value as SinceKey)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300 focus:border-indigo-600 focus:outline-none"
          >
            {(Object.keys(SINCE_LABELS) as SinceKey[]).map((k) => (
              <option key={k} value={k}>
                {SINCE_LABELS[k]}
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

      {/* Error */}
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
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : allItems.length === 0 ? (
        <EmptyState
          title="No actions yet"
          hint={
            hasFilters
              ? "No actions match the current filters."
              : "Response actions appear here once incidents are correlated and auto-actions execute."
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
        <ActionTable items={allItems} />
      )}
    </div>
  )
}
