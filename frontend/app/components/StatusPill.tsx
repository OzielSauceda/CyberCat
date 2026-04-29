import type { ActionStatus, IncidentStatus } from "../lib/api"

const styles: Record<IncidentStatus | ActionStatus, string> = {
  // incident statuses
  new:           "text-zinc-300 bg-zinc-800 border-zinc-600",
  triaged:       "text-zinc-200 bg-zinc-700 border-zinc-500",
  investigating: "text-blue-300 bg-blue-950 border-blue-700",
  contained:     "text-amber-300 bg-amber-950 border-amber-700",
  resolved:      "text-emerald-300 bg-emerald-950 border-emerald-700",
  closed:        "text-zinc-500 bg-zinc-900 border-zinc-700",
  reopened:      "text-purple-300 bg-purple-950 border-purple-700",
  // action statuses
  proposed:      "text-blue-300 bg-blue-950 border-blue-700",
  executed:      "text-emerald-300 bg-emerald-950 border-emerald-700",
  failed:        "text-red-300 bg-red-950 border-red-700",
  skipped:       "text-zinc-500 bg-zinc-900 border-zinc-700",
  reverted:      "text-amber-300 bg-amber-950 border-amber-700",
  partial:       "text-yellow-300 bg-yellow-950 border-yellow-700",
}

export function StatusPill({ status }: { status: IncidentStatus | ActionStatus }) {
  const cls = styles[status] ?? "text-zinc-400 bg-zinc-900 border-zinc-700"
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-case font-medium uppercase tracking-widest ${cls}`}
    >
      {status}
    </span>
  )
}
