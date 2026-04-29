"use client"

import * as Tooltip from "@radix-ui/react-tooltip"
import Link from "next/link"
import type { ActionClassification } from "../lib/api"
import { ACTION_CLASSIFICATION_LABELS } from "../lib/labels"

// Short display label keeps the chip compact even when the friendly label is long.
const SHORT: Record<ActionClassification, string> = {
  auto_safe: "Auto-safe",
  suggest_only: "Needs approval",
  reversible: "Reversible",
  disruptive: "Disruptive",
}

const classes: Record<ActionClassification, string> = {
  auto_safe: "text-emerald-300 bg-emerald-950 border-emerald-800",
  suggest_only: "text-sky-300 bg-sky-950 border-sky-800",
  reversible: "text-amber-300 bg-amber-950 border-amber-800",
  disruptive: "text-red-300 bg-red-950 border-red-700",
}

export function ActionClassificationBadge({
  classification,
}: {
  classification: ActionClassification
}) {
  const entry = ACTION_CLASSIFICATION_LABELS[classification]
  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={100}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={`inline-flex cursor-help items-center rounded border px-1.5 py-0.5 text-[10px] font-case font-medium uppercase tracking-widest ${classes[classification]}`}
          >
            {SHORT[classification]}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={6}
            className="z-50 max-w-[280px] rounded border border-dossier-paperEdge bg-dossier-paper px-3 py-2.5 shadow-xl"
          >
            <p className="mb-1 font-case text-[11px] text-dossier-ink">{entry.label}</p>
            <p className="text-xs leading-snug text-dossier-ink/60">{entry.plain}</p>
            {entry.slug ? (
              <Link
                href={`/help#${entry.slug}`}
                className="mt-1.5 block text-[10px] text-dossier-evidenceTape/60 transition-colors hover:text-dossier-evidenceTape"
              >
                Read more →
              </Link>
            ) : null}
            <Tooltip.Arrow className="fill-dossier-paperEdge" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
