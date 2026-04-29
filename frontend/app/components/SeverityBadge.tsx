"use client"

import * as Tooltip from "@radix-ui/react-tooltip"
import type { Severity } from "../lib/api"
import { SEVERITY_ABBREV, SEVERITY_LABELS } from "../lib/labels"

const styles: Record<Severity, string> = {
  info:     "text-dossier-ink/50 border-dossier-paperEdge bg-dossier-stamp",
  low:      "text-sky-400 border-sky-800/60 bg-sky-950/40",
  medium:   "text-cyber-yellow border-amber-700/60 bg-amber-950/30",
  high:     "text-cyber-orange border-orange-800/60 bg-orange-950/30",
  critical: "text-dossier-redaction border-dossier-redaction/50 bg-red-950/40",
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const entry = SEVERITY_LABELS[severity]
  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={100}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={`inline-flex cursor-help items-center rounded border px-2 py-0.5 font-case font-bold tracking-widest uppercase text-[10px] ${styles[severity]}`}
          >
            {SEVERITY_ABBREV[severity]}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={6}
            className="z-50 max-w-[260px] rounded border border-dossier-paperEdge bg-dossier-paper px-3 py-2.5 shadow-xl"
          >
            <p className="mb-1 font-case text-[11px] text-dossier-ink">{entry.label} severity</p>
            <p className="text-xs leading-snug text-dossier-ink/60">{entry.plain}</p>
            <Tooltip.Arrow className="fill-dossier-paperEdge" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
