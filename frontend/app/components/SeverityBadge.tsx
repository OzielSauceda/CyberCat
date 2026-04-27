import type { Severity } from "../lib/api"

const styles: Record<Severity, string> = {
  info: "text-zinc-400 bg-zinc-800 border-zinc-700",
  low: "text-sky-300 bg-sky-950 border-sky-800",
  medium: "text-amber-300 bg-amber-950 border-amber-800",
  high: "text-orange-300 bg-orange-950 border-orange-800",
  critical: "text-red-300 bg-red-950 border-red-700",
}

const labels: Record<Severity, string> = {
  info: "INFO",
  low: "LOW",
  medium: "MED",
  high: "HIGH",
  critical: "CRIT",
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-semibold font-mono tracking-wider ${styles[severity]}`}
    >
      {labels[severity]}
    </span>
  )
}
