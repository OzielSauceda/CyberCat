"use client"

import { useCallback, useEffect, useState } from "react"
import { ActionClassificationBadge } from "../../components/ActionClassificationBadge"
import { EntityChip } from "../../components/EntityChip"
import { Panel } from "../../components/Panel"
import {
  ApiError,
  getRecommendedActions,
  type EntityKind,
  type RecommendedAction,
} from "../../lib/api"
import { useCanMutate } from "../../lib/SessionContext"

interface RecommendedActionsPanelProps {
  incidentId: string
  /** Changes when the incident's actions change so the panel refetches in lockstep. */
  refreshKey: string
  onUseRecommendation: (rec: RecommendedAction) => void
}

const PARAM_ENTITY_KIND: Partial<Record<string, EntityKind>> = {
  block_observable: "ip",
  quarantine_host_lab: "host",
  flag_host_in_lab: "host",
  invalidate_lab_session: "host",
  request_evidence: "host",
}

function humanizeAction(rec: RecommendedAction): string {
  const target = rec.target_summary
  switch (rec.kind) {
    case "block_observable":
      return target ? `Block ${target}` : "Block observable"
    case "quarantine_host_lab":
      return target ? `Quarantine ${target}` : "Quarantine host"
    case "flag_host_in_lab":
      return target ? `Flag ${target}` : "Flag host"
    case "invalidate_lab_session":
      return target ? `Invalidate session ${target}` : "Invalidate session"
    case "request_evidence": {
      const ek = String(rec.params.evidence_kind ?? "evidence").replace(/_/g, " ")
      return target ? `Request ${ek} from ${target}` : `Request ${ek}`
    }
    default:
      return rec.kind.replace(/_/g, " ")
  }
}

export function RecommendedActionsPanel({
  incidentId,
  refreshKey,
  onUseRecommendation,
}: RecommendedActionsPanelProps) {
  const canMutate = useCanMutate()
  const [recs, setRecs] = useState<RecommendedAction[] | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchRecs = useCallback(async () => {
    setError(null)
    try {
      const data = await getRecommendedActions(incidentId)
      setRecs(data)
    } catch (err) {
      setError(err instanceof ApiError ? err : new Error("Could not load recommendations."))
    } finally {
      setLoading(false)
    }
  }, [incidentId])

  useEffect(() => {
    setLoading(true)
    void fetchRecs()
  }, [fetchRecs, refreshKey])

  const isEntityChipParam = (rec: RecommendedAction): boolean => {
    return rec.kind in PARAM_ENTITY_KIND && Boolean(rec.target_summary)
  }

  return (
    <Panel title="Recommended response" count={recs?.length}>
      {loading && recs === null ? (
        <p className="text-sm text-zinc-500">Loading recommendations…</p>
      ) : error ? (
        <div className="flex items-center gap-2 text-sm text-zinc-400">
          <span>Could not load recommendations.</span>
          <button
            onClick={() => { setLoading(true); void fetchRecs() }}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
          >
            Retry
          </button>
        </div>
      ) : !recs || recs.length === 0 ? (
        <p className="text-sm text-zinc-500">No recommended actions for this incident.</p>
      ) : (
        <div className="space-y-3">
          {recs.map((rec, i) => (
            <div
              key={`${rec.kind}-${rec.priority}-${i}`}
              className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
            >
              <div className="flex flex-wrap items-center gap-2 mb-1.5">
                <ActionClassificationBadge classification={rec.classification} />
                <span className="font-medium text-sm text-zinc-100">
                  {humanizeAction(rec)}
                </span>
                <span
                  className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400"
                  title="Recommendation priority"
                >
                  #{rec.priority}
                </span>
                <button
                  onClick={() => onUseRecommendation(rec)}
                  disabled={!canMutate}
                  title={!canMutate ? "Read-only role" : undefined}
                  className="ml-auto rounded bg-indigo-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Use this
                </button>
              </div>
              <p className="text-sm text-zinc-300 mb-2 leading-snug">
                {rec.summary || rec.rationale}
              </p>
              {rec.summary && rec.rationale && rec.summary !== rec.rationale ? (
                <details className="mb-2 group">
                  <summary className="cursor-pointer font-case text-[10px] uppercase tracking-widest text-zinc-500 transition-colors hover:text-dossier-evidenceTape">
                    Why this works
                  </summary>
                  <p className="mt-1.5 text-xs leading-snug text-zinc-400 font-mono">
                    {rec.rationale}
                  </p>
                </details>
              ) : null}
              {isEntityChipParam(rec) && (
                <div className="flex flex-wrap gap-1">
                  <EntityChip
                    kind={PARAM_ENTITY_KIND[rec.kind]!}
                    naturalKey={rec.target_summary}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
