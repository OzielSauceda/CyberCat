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

type SinceKey = "1h" | "24h" | "7d" | "all"
const sinceKeys: SinceKey[] = ["1h", "24h", "7d", "all"]
const sinceLabels: Record<SinceKey, string> = {
  "1h": "1h", "24h": "24h", "7d": "7d", all: "all",
}

function sinceIso(key: SinceKey): string {
  if (key === "1h")  return new Date(Date.now() - 3_600_000).toISOString()
  if (key === "24h") return new Date(Date.now() - 86_400_000).toISOString()
  if (key === "7d")  return new Date(Date.now() - 604_800_000).toISOString()
  return ""
}

function AttackTagById({ id }: { id: string }) {
  const entry  = useAttackEntry(id)
  const hasDot = id.includes(".")
  return (
    <AttackTag
      technique={hasDot ? id.split(".")[0] : id}
      subtechnique={hasDot ? id : null}
      source="rule_derived"
      name={entry?.name}
    />
  )
}

// ── Filter chip ───────────────────────────────────────────────────────────────

function Chip({
  label, active, onClick,
}: {
  label: string; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="px-2.5 py-1 font-case text-[11px] font-semibold uppercase tracking-wide border transition-all duration-150"
      style={{
        borderColor: active ? "#00d4ff55" : "#0c1b2e",
        background:  active ? "#00d4ff12" : "transparent",
        color:       active ? "#00d4ff"   : "#cdd6df28",
      }}
    >
      {label}
    </button>
  )
}

// ── Detection row ─────────────────────────────────────────────────────────────

function DetectionRow({ detection }: { detection: DetectionItem }) {
  const inner = (
    <article className="border border-dossier-paperEdge bg-dossier-stamp overflow-hidden transition-all duration-150 hover:border-dossier-evidenceTape/20 hover:bg-dossier-paperEdge/20 group">
      {/* Main row */}
      <div className="flex items-center gap-4 px-4 py-3 min-w-0">
        {/* Rule ID */}
        <span className="flex-1 font-mono text-sm font-medium text-dossier-ink/80 group-hover:text-dossier-ink transition-colors truncate min-w-0">
          {detection.rule_id}
        </span>

        {/* Source */}
        <span
          className={`shrink-0 font-mono text-[11px] uppercase tracking-widest px-1.5 py-0.5 border ${
            detection.rule_source === "sigma"
              ? "border-violet-800/50 text-violet-400/75 bg-violet-950/25"
              : "border-blue-800/50 text-blue-400/75 bg-blue-950/25"
          }`}
        >
          {detection.rule_source}
        </span>

        {/* Severity */}
        <div className="shrink-0">
          <SeverityBadge severity={detection.severity_hint} />
        </div>

        {/* Confidence */}
        <span className="shrink-0 flex items-center gap-2 hidden sm:flex">
          <span className="font-mono text-[11px] text-dossier-ink/25">conf</span>
          <ConfidenceBar value={detection.confidence_hint} />
        </span>

        {/* Time */}
        <span className="shrink-0 font-mono text-xs text-dossier-ink/25 whitespace-nowrap">
          <RelativeTime at={detection.created_at} />
        </span>

        {/* Incident link indicator */}
        {detection.incident_id && (
          <span className="shrink-0 font-mono text-xs text-dossier-evidenceTape/50">
            → incident
          </span>
        )}
      </div>

      {/* ATT&CK tags — only shown if present */}
      {detection.attack_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-2.5 pt-2 border-t border-dossier-paperEdge/40">
          {detection.attack_tags.map((tag) => (
            <AttackTagById key={tag} id={tag} />
          ))}
        </div>
      )}
    </article>
  )

  if (detection.incident_id) {
    return (
      <Link href={`/incidents/${detection.incident_id}`} className="block">
        {inner}
      </Link>
    )
  }
  return inner
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DetectionsPage() {
  const [ruleSource,    setRuleSource]    = useState<DetectionRuleSource | "">("")
  const [ruleId,        setRuleId]        = useState("")
  const [sinceKey,      setSinceKey]      = useState<SinceKey>("24h")
  const [extraItems,    setExtraItems]    = useState<DetectionItem[]>([])
  const [nextCursor,    setNextCursor]    = useState<string | null>(null)
  const [loadingMore,   setLoadingMore]   = useState(false)
  const [loadMoreError, setLoadMoreError] = useState<Error>()

  const fetcher = useCallback(
    () => listDetections({
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

  useEffect(() => { if (data) setNextCursor(data.next_cursor) }, [data])
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
  const clearFilters = () => { setRuleSource(""); setRuleId(""); setSinceKey("24h") }
  const allItems = [...(data?.items ?? []), ...extraItems]

  return (
    <div className="space-y-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-case text-2xl font-bold uppercase tracking-wider text-dossier-ink">
            Detections
          </h1>
          <p className="mt-0.5 font-mono text-xs text-dossier-ink/30">
            {data
              ? `${allItems.length} rule${allItems.length !== 1 ? "s" : ""} fired${hasFilters ? " · filtered" : ""}`
              : "Loading…"}
          </p>
        </div>
        {error instanceof ApiError && (
          <span className="font-mono text-xs text-cyber-orange/70">⚠ backend unreachable</span>
        )}
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">source</span>
        {(["", "sigma", "py"] as const).map((s) => (
          <Chip
            key={s || "all"}
            label={s || "any"}
            active={ruleSource === s}
            onClick={() => setRuleSource(s as DetectionRuleSource | "")}
          />
        ))}
        <div className="w-px h-4 bg-dossier-paperEdge mx-2" />
        <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">since</span>
        {sinceKeys.map((k) => (
          <Chip
            key={k}
            label={sinceLabels[k]}
            active={sinceKey === k}
            onClick={() => setSinceKey(k)}
          />
        ))}
        <div className="w-px h-4 bg-dossier-paperEdge mx-2" />
        <input
          type="text"
          value={ruleId}
          onChange={(e) => setRuleId(e.target.value)}
          placeholder="filter rule id…"
          className="border border-dossier-paperEdge bg-dossier-stamp px-3 py-1 font-mono text-xs text-dossier-ink/70 placeholder-dossier-ink/20 outline-none focus:border-dossier-evidenceTape/40 transition-colors"
        />
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
          {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : allItems.length === 0 ? (
        <EmptyState
          title="No detections yet"
          hint={
            hasFilters
              ? "No detections match the current filters."
              : "Events haven't arrived yet. Start the agent or send events through the API to see detection rules fire."
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
            {allItems.map((d) => (
              <DetectionRow key={d.id} detection={d} />
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
