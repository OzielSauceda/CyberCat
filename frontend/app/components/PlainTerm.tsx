"use client"

import * as Tooltip from "@radix-ui/react-tooltip"
import Link from "next/link"
import { GLOSSARY, type GlossarySlug } from "../lib/glossary"

interface PlainTermProps {
  // Plain-language label shown as primary text.
  primary: string
  // Optional technical term shown inline as a small muted secondary label.
  // When omitted, only the plain label renders (still tooltip-wrapped if slug given).
  technical?: string
  // Glossary entry to surface in the hover tooltip.
  slug?: GlossarySlug
  // Override of the tooltip body (useful for context-specific definitions
  // that don't have a glossary entry).
  plain?: string
  // Inline class overrides for the primary span.
  className?: string
}

// Renders the hybrid pattern: plain label leads, technical term appears as
// muted inline secondary, hovering reveals a definition. Reuses the Radix
// tooltip surface from JargonTerm.
export function PlainTerm({
  primary,
  technical,
  slug,
  plain,
  className,
}: PlainTermProps) {
  const entry = slug ? GLOSSARY[slug] : null
  const tooltipBody = plain ?? entry?.short ?? ""
  const hasTooltip = Boolean(tooltipBody)

  const inner = (
    <span className={className}>
      <span>{primary}</span>
      {technical ? (
        <span className="ml-1.5 font-mono text-[10px] uppercase tracking-wider text-dossier-ink/40">
          {technical}
        </span>
      ) : null}
    </span>
  )

  if (!hasTooltip) {
    return inner
  }

  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={100}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span className="cursor-help border-b border-dotted border-dossier-evidenceTape/40 transition-colors hover:border-dossier-evidenceTape/80">
            {inner}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={6}
            className="z-50 max-w-[280px] rounded border border-dossier-paperEdge bg-dossier-paper px-3 py-2.5 shadow-xl"
          >
            {entry ? (
              <p className="mb-1 font-case text-[11px] text-dossier-ink">{entry.title}</p>
            ) : null}
            <p className="text-xs leading-snug text-dossier-ink/60">{tooltipBody}</p>
            {slug ? (
              <Link
                href={`/help#${slug}`}
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
