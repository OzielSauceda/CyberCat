"use client"

import * as Tooltip from "@radix-ui/react-tooltip"
import type { ActionStatus, IncidentStatus } from "../lib/api"
import { ACTION_STATUS_LABELS, INCIDENT_STATUS_LABELS } from "../lib/labels"

const styles: Record<IncidentStatus | ActionStatus, string> = {
  // incident statuses
  new:           "text-zinc-300 bg-zinc-800 border-zinc-600",
  triaged:       "text-zinc-200 bg-zinc-700 border-zinc-500",
  investigating: "text-blue-300 bg-blue-950 border-blue-700",
  contained:     "text-amber-300 bg-amber-950 border-amber-700",
  resolved:      "text-emerald-300 bg-emerald-950 border-emerald-700",
  closed:        "text-zinc-500 bg-zinc-900 border-zinc-700",
  reopened:      "text-purple-300 bg-purple-950 border-purple-700",
  // Phase 20 §C — merged source. Cyber-orange to match merge action color.
  merged:        "text-cyber-orange bg-cyber-orange/10 border-cyber-orange/40",
  // action statuses
  proposed:      "text-blue-300 bg-blue-950 border-blue-700",
  executed:      "text-emerald-300 bg-emerald-950 border-emerald-700",
  failed:        "text-red-300 bg-red-950 border-red-700",
  skipped:       "text-zinc-500 bg-zinc-900 border-zinc-700",
  reverted:      "text-amber-300 bg-amber-950 border-amber-700",
  partial:       "text-yellow-300 bg-yellow-950 border-yellow-700",
}

const INCIDENT_STATUSES = new Set([
  "new",
  "triaged",
  "investigating",
  "contained",
  "resolved",
  "closed",
  "reopened",
  "merged",
])

function lookup(status: IncidentStatus | ActionStatus): { label: string; plain: string } {
  if (INCIDENT_STATUSES.has(status)) {
    const e = INCIDENT_STATUS_LABELS[status as IncidentStatus]
    return { label: e.label, plain: e.plain }
  }
  const e = ACTION_STATUS_LABELS[status as ActionStatus]
  return { label: e.label, plain: e.plain }
}

export function StatusPill({ status }: { status: IncidentStatus | ActionStatus }) {
  const cls = styles[status] ?? "text-zinc-400 bg-zinc-900 border-zinc-700"
  const { label, plain } = lookup(status)

  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={100}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={`inline-flex cursor-help items-center rounded border px-2 py-0.5 text-[10px] font-case font-medium uppercase tracking-widest ${cls}`}
          >
            {label}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={6}
            className="z-50 max-w-[260px] rounded border border-dossier-paperEdge bg-dossier-paper px-3 py-2.5 shadow-xl"
          >
            <p className="mb-1 font-case text-[11px] text-dossier-ink">{label}</p>
            <p className="text-xs leading-snug text-dossier-ink/60">{plain}</p>
            <p className="mt-1 font-mono text-[10px] text-dossier-ink/30">{status}</p>
            <Tooltip.Arrow className="fill-dossier-paperEdge" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
