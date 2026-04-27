"use client"

import { useCallback, useState } from "react"
import {
  collectEvidenceRequest,
  dismissEvidenceRequest,
  listEvidenceRequests,
  type EvidenceRequest,
  type EvidenceStatus,
} from "../lib/api"
import { useCanMutate } from "../lib/SessionContext"
import { usePolling } from "../lib/usePolling"
import { EmptyState } from "./EmptyState"
import { Panel } from "./Panel"
import { RelativeTime } from "./RelativeTime"

const statusStyles: Record<EvidenceStatus, string> = {
  open: "text-amber-300 bg-amber-950 border-amber-800",
  collected: "text-green-300 bg-green-950 border-green-800",
  dismissed: "text-zinc-500 bg-zinc-900 border-zinc-700",
}

const kindLabels: Record<string, string> = {
  triage_log: "Triage log",
  process_list: "Process list",
  network_connections: "Network connections",
  memory_snapshot: "Memory snapshot",
}

export function EvidenceRequestsPanel({ incidentId }: { incidentId: string }) {
  const fetcher = useCallback(() => listEvidenceRequests(incidentId), [incidentId])
  const { data, loading, refetch } = usePolling(fetcher, 8_000)
  const canMutate = useCanMutate()
  const [busy, setBusy] = useState<string | null>(null)

  const items = data?.items ?? []

  async function handleCollect(id: string) {
    setBusy(id)
    try {
      await collectEvidenceRequest(id)
      refetch()
    } finally {
      setBusy(null)
    }
  }

  async function handleDismiss(id: string) {
    setBusy(id)
    try {
      await dismissEvidenceRequest(id)
      refetch()
    } finally {
      setBusy(null)
    }
  }

  return (
    <Panel title="Evidence requests" count={items.length}>
      {loading && items.length === 0 ? (
        <div className="h-8 w-full animate-pulse rounded bg-zinc-800" />
      ) : items.length === 0 ? (
        <EmptyState title="No evidence requests" />
      ) : (
        <div className="space-y-2">
          {items.map((er: EvidenceRequest) => (
            <div
              key={er.id}
              className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
            >
              <div className="flex flex-wrap items-center gap-2 mb-1.5">
                <span className="font-mono text-sm text-zinc-100">
                  {kindLabels[er.kind] ?? er.kind}
                </span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-xs font-medium ${statusStyles[er.status]}`}
                >
                  {er.status}
                </span>
                <span className="ml-auto text-xs text-zinc-500">
                  <RelativeTime at={er.requested_at} />
                </span>
              </div>
              {er.collected_at && (
                <p className="text-xs text-zinc-500 mb-1.5">
                  Collected <RelativeTime at={er.collected_at} />
                </p>
              )}
              {er.status === "open" && (
                <div className="flex gap-2 mt-2">
                  <button
                    disabled={busy === er.id || !canMutate}
                    title={!canMutate ? "Read-only role" : undefined}
                    onClick={() => handleCollect(er.id)}
                    className="rounded bg-green-900 px-2 py-1 text-xs text-green-200 hover:bg-green-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Mark collected
                  </button>
                  <button
                    disabled={busy === er.id || !canMutate}
                    title={!canMutate ? "Read-only role" : undefined}
                    onClick={() => handleDismiss(er.id)}
                    className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
