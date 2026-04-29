import type { Severity } from "../lib/api"

const styles: Record<Severity, string> = {
  info:     "text-dossier-ink/50 border-dossier-paperEdge bg-dossier-stamp",
  low:      "text-sky-400 border-sky-800/60 bg-sky-950/40",
  medium:   "text-cyber-yellow border-amber-700/60 bg-amber-950/30",
  high:     "text-cyber-orange border-orange-800/60 bg-orange-950/30",
  critical: "text-dossier-redaction border-dossier-redaction/50 bg-red-950/40",
}

const labels: Record<Severity, string> = {
  info:     "INFO",
  low:      "LOW",
  medium:   "MED",
  high:     "HIGH",
  critical: "CRIT",
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 font-case font-bold tracking-widest uppercase text-[10px] ${styles[severity]}`}
    >
      {labels[severity]}
    </span>
  )
}
