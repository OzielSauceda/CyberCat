"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { AttackTag } from "../components/AttackTag"
import { ConfidenceBar } from "../components/ConfidenceBar"
import { EmptyState } from "../components/EmptyState"
import { ErrorState } from "../components/ErrorState"
import { RelativeTime } from "../components/RelativeTime"
import { SeverityBadge } from "../components/SeverityBadge"
import { SkeletonCard } from "../components/Skeleton"
import {
  ApiError,
  listDetections,
  type DetectionItem,
  type DetectionRuleSource,
} from "../lib/api"
import { useAttackEntry } from "../lib/attackCatalog"
import { useStream } from "../lib/useStream"

const SINCE_OPTIONS = [
  { label: "Last 1h", value: () => new Date(Date.now() - 3600_000).toISOString() },
  { label: "Last 24h", value: () => new Date(Date.now() - 86400_000).toISOString() },
  { label: "Last 7d", value: () => new Date(Date.now() - 604800_000).toISOString() },
  { label: "All time", value: () => "" },
] as const

type SinceKey = "1h" | "24h" | "7d" | "all"
const sinceKeys: SinceKey[] = ["1h", "24h", "7d", "all"]
const sinceLabels: Record<SinceKey, string> = {
  "1h": "Last 1h",
  "24h": "Last 24h",
  "7d": "Last 7d",
  all: "All time",
}

function sinceIso(key: SinceKey): string {
  if (key === "1h") return new Date(Date.now() - 3600_000).toISOString()
  if (key === "24h") return new Date(Date.now() - 86400_000).toISOString()
  if (key === "7d") return new Date(Date.now() - 604800_000).toISOString()
  return ""
}

function AttackTagById({ id }: { id: string }) {
  const entry = useAttackEntry(id)
  const hasDot = id.includes(".")
  const technique = hasDot ? id.split(".")[0] : id
  const subtechnique = hasDot ? id : null
  return (
    <AttackTag
      technique={technique}
      subtechnique={subtechnique}
      source="rule_derived"
      name={entry?.name}
    />
  )
}

function DetectionCard({ detection }: { detection: DetectionItem }) {
  const inner = (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700 hover:bg-zinc-800/60">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-medium text-zinc-100">{detection.rule_id}</span>
        <span
          className={`rounded border px-1.5 py-0.5 text-xs font-mono ${
            detection.rule_source === "sigma"
              ? "border-violet-800 bg-violet-950 text-violet-300"
              : "border-blue-800 bg-blue-950 text-blue-300"
          }`}
        >
          {detection.rule_source}
        </span>
        <span className="text-xs text-zinc-500">v{detection.rule_version}</span>
        <span className="ml-auto text-xs text-zinc-500">
          <RelativeTime at={detection.created_at} />
        </span>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-zinc-400">
        <SeverityBadge severity={detection.severity_hint} />
        <span className="flex items-center gap-1">
          Confidence <ConfidenceBar value={detection.confidence_hint} />
        </span>
      </div>

      {detection.attack_tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {detection.attack_tags.map((tag) => (
            <AttackTagById key={tag} id={tag} />
          ))}
        </div>
      )}

      {detection.incident_id && (
        <div className="mt-2 text-xs text-indigo-400">→ incident linked</div>
      )}
    </article>
  )

  if (detection.incident_id) {
    return (
      <Link href={`/incidents/${detection.incident_id}`} className="block group">
        {inner}
      </Link>
    )
  }
  return inner
}

export default function DetectionsPage() {
  const [ruleSource, setRuleSource] = useState<DetectionRuleSource | "">("")
  const [ruleId, setRuleId] = useState("")
  const [sinceKey, setSinceKey] = useState<SinceKey>("24h")
  const [extraItems, setExtraItems] = useState<DetectionItem[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState<Error>()

  const fetcher = useCallback(
    () =>
      listDetections({
        rule_source: ruleSource || undefined,
        rule_id: ruleId || undefined,
        since: sinceIso(sinceKey) || undefined,
        limit: 50,
      }),
    [ruleSource, ruleId, sinceKey],
  )

  const { data, error, loading, refetch } = useStream({
    topics: ["detections"],
    fetcher,
    shouldRefetch: (e) => e.type === "detection.fired",
  })

  useEffect(() => {
    if (data) setNextCursor(data.next_cursor)
  }, [data])

  useEffect(() => {
    setExtraItems([])
    setNextCursor(null)
    setLoadMoreError(undefined)
  }, [ruleSource, ruleId, sinceKey])

  const handleLoadMore = async () => {
    if (!nextCursor) return
    setLoadingMore(true)
    setLoadMoreError(undefined)
    try {
      const page = await listDetections({
        rule_source: ruleSource || undefined,
        rule_id: ruleId || undefined,
        since: sinceIso(sinceKey) || undefined,
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

  const hasFilters = ruleSource !== "" || ruleId !== "" || sinceKey !== "24h"
  const clearFilters = () => {
    setRuleSource("")
    setRuleId("")
    setSinceKey("24h")
  }

  const allItems = [...(data?.items ?? []), ...extraItems]

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Detections</h1>
          {data && (
            <p className="mt-0.5 text-sm text-zinc-500">
              {allItems.length} loaded{hasFilters && " (filtered)"}
            </p>
          )}
        </div>
        {error instanceof ApiError && (
          <span className="text-xs text-amber-400">Can&apos;t reach the backend — showing last saved data</span>
        )}
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Source:</span>
          <div className="flex gap-1">
            {(["", "sigma", "py"] as const).map((s) => (
              <button
                key={s || "all"}
                onClick={() => setRuleSource(s as DetectionRuleSource | "")}
                className={`rounded-full border px-2.5 py-0.5 text-xs capitalize transition-colors ${
                  ruleSource === s
                    ? "border-indigo-700 bg-indigo-950 text-indigo-300"
                    : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {s || "any"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Rule:</span>
          <input
            type="text"
            value={ruleId}
            onChange={(e) => setRuleId(e.target.value)}
            placeholder="rule_id filter…"
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300 focus:border-indigo-600 focus:outline-none w-40"
          />
        </div>

        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Since:</span>
          <select
            value={sinceKey}
            onChange={(e) => setSinceKey(e.target.value as SinceKey)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-300 focus:border-indigo-600 focus:outline-none"
          >
            {sinceKeys.map((k) => (
              <option key={k} value={k}>
                {sinceLabels[k]}
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

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : allItems.length === 0 ? (
        <EmptyState
          title="No detections yet"
          hint={hasFilters ? "No detections match the current filters." : "Events haven't arrived yet. Start the agent or send events through the API to see detection rules fire."}
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
            {allItems.map((d) => (
              <DetectionCard key={d.id} detection={d} />
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
