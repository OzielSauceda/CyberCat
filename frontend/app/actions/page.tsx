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
  "", "auto_safe", "suggest_only", "reversible", "disruptive",
]

const STATUS_OPTIONS: Array<ActionStatus | ""> = [
  "", "proposed", "executed", "failed", "skipped", "reverted",
]

type SinceKey = "1h" | "24h" | "7d" | "all"
const SINCE_LABELS: Record<SinceKey, string> = {
  "1h": "1h", "24h": "24h", "7d": "7d", all: "all",
}

function sinceIso(key: SinceKey): string | undefined {
  if (key === "1h")  return new Date(Date.now() - 3_600_000).toISOString()
  if (key === "24h") return new Date(Date.now() - 86_400_000).toISOString()
  if (key === "7d")  return new Date(Date.now() - 604_800_000).toISOString()
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

// ── Action row ────────────────────────────────────────────────────────────────

function ActionRow({ action }: { action: ActionSummary }) {
  const target = targetFromParams(action.params)
  return (
    <div className="flex items-center gap-4 border border-dossier-paperEdge bg-dossier-stamp px-4 py-3 overflow-hidden transition-colors hover:bg-dossier-paperEdge/20">
      {/* Classification badge */}
      <div className="shrink-0">
        <ActionClassificationBadge classification={action.classification} />
      </div>

      {/* Kind */}
      <span className="flex-1 font-mono text-sm text-dossier-ink/80 truncate min-w-0">
        {action.kind}
      </span>

      {/* Status */}
      <div className="shrink-0">
        <StatusPill status={action.status} />
      </div>

      {/* Target */}
      <span className="shrink-0 font-mono text-xs text-dossier-ink/35 hidden md:block max-w-[150px] truncate">
        {target ?? <span className="text-dossier-ink/15">—</span>}
      </span>

      {/* Proposed by */}
      <span
        className={`shrink-0 font-mono text-xs px-1.5 py-0.5 border hidden lg:block ${
          action.proposed_by === "system"
            ? "border-dossier-paperEdge text-dossier-ink/30"
            : "border-dossier-evidenceTape/30 text-dossier-evidenceTape/60"
        }`}
      >
        {action.proposed_by}
      </span>

      {/* Time */}
      <span className="shrink-0 font-mono text-xs text-dossier-ink/25 whitespace-nowrap">
        <RelativeTime at={action.proposed_at} />
      </span>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ActionsPage() {
  const [statusFilter, setStatusFilter] = useState<ActionStatus | "">("")
  const [classFilter,  setClassFilter]  = useState<ActionClassification | "">("")
  const [kindFilter,   setKindFilter]   = useState<ActionKind | "">("")
  const [sinceKey,     setSinceKey]     = useState<SinceKey>("24h")

  const fetcher = useCallback(
    () => listActions({
      status:         statusFilter || undefined,
      classification: classFilter  || undefined,
      kind:           kindFilter   || undefined,
      since:          sinceIso(sinceKey),
      limit:          50,
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
    <div className="space-y-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-case text-2xl font-bold uppercase tracking-wider text-dossier-ink">
            Response Actions
          </h1>
          <p className="mt-0.5 font-mono text-xs text-dossier-ink/30">
            {data
              ? `${allItems.length} action${allItems.length !== 1 ? "s" : ""}${hasFilters ? " · filtered" : ""}`
              : "Loading…"}
          </p>
        </div>
        <p className="font-mono text-[11px] text-dossier-ink/25 text-right max-w-[220px] leading-relaxed hidden sm:block">
          To run or undo actions, open an incident and use the Response tab.
        </p>
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────── */}
      <div className="space-y-2">
        {/* Row 1: status + class */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">status</span>
          {STATUS_OPTIONS.map((s) => (
            <Chip
              key={s || "all"}
              label={s || "any"}
              active={statusFilter === s}
              onClick={() => setStatusFilter(s as ActionStatus | "")}
            />
          ))}
          <div className="w-px h-4 bg-dossier-paperEdge mx-2" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">class</span>
          {CLASSIFICATION_OPTIONS.map((c) => (
            <Chip
              key={c || "all"}
              label={c ? c.replace("_", " ") : "any"}
              active={classFilter === c}
              onClick={() => setClassFilter(c as ActionClassification | "")}
            />
          ))}
        </div>

        {/* Row 2: since + kind */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">since</span>
          {(Object.keys(SINCE_LABELS) as SinceKey[]).map((k) => (
            <Chip
              key={k}
              label={SINCE_LABELS[k]}
              active={sinceKey === k}
              onClick={() => setSinceKey(k)}
            />
          ))}
          <div className="w-px h-4 bg-dossier-paperEdge mx-2" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">kind</span>
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value as ActionKind | "")}
            className="border border-dossier-paperEdge bg-dossier-stamp px-3 py-1 font-mono text-xs text-dossier-ink/60 outline-none focus:border-dossier-evidenceTape/40 transition-colors"
          >
            <option value="">any</option>
            {ACTION_KINDS.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="ml-auto font-mono text-[11px] uppercase tracking-widest text-dossier-redaction/40 hover:text-dossier-redaction transition-colors"
            >
              × clear
            </button>
          )}
        </div>
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
          {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : allItems.length === 0 ? (
        <EmptyState
          title="No actions yet"
          hint={
            hasFilters
              ? "No actions match the current filters."
              : "Actions show up here once CyberCat starts processing incidents. Automated ones run on their own; others need your approval first."
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
        <div className="space-y-1">
          {allItems.map((a) => (
            <ActionRow key={a.id} action={a} />
          ))}
        </div>
      )}
    </div>
  )
}
