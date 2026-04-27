"use client"

import Link from "next/link"
import { use, useCallback } from "react"
import { ConfidenceBar } from "../../components/ConfidenceBar"
import { EmptyState } from "../../components/EmptyState"
import { ErrorState } from "../../components/ErrorState"
import { JsonBlock } from "../../components/JsonBlock"
import { Panel } from "../../components/Panel"
import { RelativeTime } from "../../components/RelativeTime"
import { SeverityBadge } from "../../components/SeverityBadge"
import { SkeletonRow } from "../../components/Skeleton"
import { StatusPill } from "../../components/StatusPill"
import { BlockedObservablesBadge } from "../../components/BlockedObservablesBadge"
import { ApiError, getEntity, type EntityKind } from "../../lib/api"
import { usePolling } from "../../lib/usePolling"

const kindStyles: Record<EntityKind, string> = {
  user: "text-indigo-300 bg-indigo-950 border-indigo-800",
  host: "text-violet-300 bg-violet-950 border-violet-800",
  ip: "text-cyan-300 bg-cyan-950 border-cyan-800",
  process: "text-lime-300 bg-lime-950 border-lime-800",
  file: "text-yellow-300 bg-yellow-950 border-yellow-800",
  observable: "text-pink-300 bg-pink-950 border-pink-800",
}

function DetailSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-7 w-1/2 rounded bg-zinc-800" />
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 3 }).map((_, i) => (
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

export default function EntityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const fetcher = useCallback(() => getEntity(id), [id])
  const { data: entity, error, loading, refetch } = usePolling(fetcher, 10_000)

  const isNotFound = error instanceof ApiError && error.status === 404

  if (isNotFound) {
    return (
      <div className="flex flex-col items-center gap-4 py-24 text-center">
        <span className="text-4xl text-zinc-700">404</span>
        <p className="text-zinc-300">Entity not found.</p>
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
      <Link
        href="/incidents"
        className="mb-4 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        ← Incidents
      </Link>

      {error && !loading && entity && (
        <div className="mb-4 flex items-center gap-2 rounded border border-amber-900 bg-amber-950/30 px-3 py-2 text-xs text-amber-400">
          <span className="font-bold">!</span>
          <span>Refresh failed — {error.message}</span>
          <button onClick={refetch} className="ml-auto underline hover:text-amber-300">
            Retry
          </button>
        </div>
      )}
      {error && !entity && !loading && <ErrorState error={error} onRetry={refetch} />}

      {loading && !entity ? (
        <DetailSkeleton />
      ) : entity ? (
        <div className="space-y-6">
          {/* Header */}
          <div>
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <span
                className={`rounded border px-2 py-0.5 font-mono text-xs font-medium ${kindStyles[entity.kind as EntityKind]}`}
              >
                {entity.kind}
              </span>
              <h1 className="text-xl font-semibold text-zinc-50 font-mono">
                {entity.natural_key}
              </h1>
              <BlockedObservablesBadge naturalKey={entity.natural_key} />
            </div>
            <div className="flex flex-wrap gap-4 text-xs text-zinc-500 mt-2">
              <span>
                First seen <RelativeTime at={entity.first_seen} />
              </span>
              <span>
                Last seen <RelativeTime at={entity.last_seen} />
              </span>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Left: attrs + events */}
            <div className="space-y-4">
              <Panel title="Attributes">
                <JsonBlock data={entity.attrs} />
              </Panel>

              <Panel title="Recent events" count={entity.recent_events.length}>
                {entity.recent_events.length === 0 ? (
                  <EmptyState title="No events recorded" />
                ) : (
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3">
                    {entity.recent_events.map((ev) => (
                      <div
                        key={ev.id}
                        className="border-b border-zinc-800 py-2.5 last:border-0"
                      >
                        <div className="flex flex-wrap items-center gap-2 text-xs mb-1">
                          <span className="font-mono text-zinc-500">
                            {new Date(ev.occurred_at).toLocaleTimeString(undefined, {
                              hour: "2-digit",
                              minute: "2-digit",
                              second: "2-digit",
                            })}
                          </span>
                          <span className="font-mono font-medium text-zinc-200">{ev.kind}</span>
                        </div>
                        <JsonBlock data={ev.normalized} />
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            </div>

            {/* Right: related incidents */}
            <div className="space-y-4">
              <Panel title="Related incidents" count={entity.related_incidents.length}>
                {entity.related_incidents.length === 0 ? (
                  <EmptyState title="No incidents linked to this entity" />
                ) : (
                  <div className="space-y-2">
                    {entity.related_incidents.map((inc) => (
                      <Link
                        key={inc.id}
                        href={`/incidents/${inc.id}`}
                        className="block rounded-lg border border-zinc-800 bg-zinc-950 p-3 hover:border-zinc-700 hover:bg-zinc-900 transition-colors"
                      >
                        <div className="flex flex-wrap items-center gap-2 mb-1.5">
                          <SeverityBadge severity={inc.severity} />
                          <StatusPill status={inc.status} />
                          <span className="ml-auto text-xs text-zinc-500">
                            <RelativeTime at={inc.opened_at} />
                          </span>
                        </div>
                        <p className="text-sm text-zinc-200 line-clamp-2">{inc.title}</p>
                        <div className="mt-1.5 flex items-center gap-3 text-xs text-zinc-500">
                          <span className="font-mono">{inc.kind.replace(/_/g, " ")}</span>
                          <ConfidenceBar value={inc.confidence} />
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
