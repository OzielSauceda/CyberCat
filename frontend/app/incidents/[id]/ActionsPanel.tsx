"use client"

import { ActionClassificationBadge } from "../../components/ActionClassificationBadge"
import { EmptyState } from "../../components/EmptyState"
import { Panel } from "../../components/Panel"
import { RelativeTime } from "../../components/RelativeTime"
import type { ActionSummary } from "../../lib/api"
import { ActionControls } from "./ActionControls"

interface ActionsPanelProps {
  incidentId: string
  actions: ActionSummary[]
  onMutated: () => void
  onPropose: () => void
}

export function ActionsPanel({ incidentId, actions, onMutated, onPropose }: ActionsPanelProps) {
  return (
    <Panel
      title="Response actions"
      count={actions.length}
      headerAction={
        <button
          onClick={onPropose}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
        >
          Propose action
        </button>
      }
    >
      {actions.length === 0 ? (
        <EmptyState
          title="No response actions"
          hint="Actions appear here when proposed or executed."
        />
      ) : (
        <div className="space-y-3">
          {actions.map((a) => (
            <div key={a.id} className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="font-mono text-xs font-medium text-zinc-200">
                  {a.kind.replace(/_/g, " ")}
                </span>
                <ActionClassificationBadge classification={a.classification} />
                <span
                  className={`rounded border px-1.5 py-0.5 text-xs ${
                    a.status === "executed"
                      ? "border-emerald-800 bg-emerald-950 text-emerald-300"
                      : a.status === "failed"
                        ? "border-red-800 bg-red-950 text-red-300"
                        : a.status === "reverted"
                          ? "border-zinc-700 bg-zinc-800 text-zinc-400"
                          : "border-zinc-700 bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {a.status}
                </span>
                {a.proposed_by === "system" && (
                  <span className="rounded border border-indigo-800 bg-indigo-950 px-1.5 py-0.5 text-xs text-indigo-300">
                    system
                  </span>
                )}
                <span className="ml-auto text-xs text-zinc-500">
                  <RelativeTime at={a.proposed_at} />
                </span>
              </div>

              <ActionControls action={a} incidentId={incidentId} onMutated={onMutated} />
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
