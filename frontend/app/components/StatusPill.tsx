import type { ActionStatus, IncidentStatus } from "../lib/api"

const styles: Record<IncidentStatus | ActionStatus, string> = {
  // incident statuses
  new: "text-zinc-300 bg-zinc-800 border-zinc-700",
  triaged: "text-zinc-200 bg-zinc-700 border-zinc-600",
  investigating: "text-blue-300 bg-blue-950 border-blue-800",
  contained: "text-amber-300 bg-amber-950 border-amber-800",
  resolved: "text-emerald-300 bg-emerald-950 border-emerald-800",
  closed: "text-zinc-500 bg-zinc-900 border-zinc-800",
  reopened: "text-purple-300 bg-purple-950 border-purple-800",
  // action statuses
  proposed: "text-blue-300 bg-blue-950 border-blue-800",
  executed: "text-emerald-300 bg-emerald-950 border-emerald-800",
  failed: "text-red-300 bg-red-950 border-red-800",
  skipped: "text-zinc-500 bg-zinc-900 border-zinc-800",
  reverted: "text-amber-300 bg-amber-950 border-amber-800",
  partial: "text-yellow-300 bg-yellow-950 border-yellow-800",
}

export function StatusPill({ status }: { status: IncidentStatus | ActionStatus }) {
  const cls = styles[status] ?? "text-zinc-400 bg-zinc-900 border-zinc-700"
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${cls}`}
    >
      {status}
    </span>
  )
}
