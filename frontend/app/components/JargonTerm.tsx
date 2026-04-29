"use client"

import * as Tooltip from "@radix-ui/react-tooltip"
import Link from "next/link"
import { GLOSSARY, type GlossarySlug } from "../lib/glossary"

interface JargonTermProps {
  slug: GlossarySlug
  children: React.ReactNode
}

export function JargonTerm({ slug, children }: JargonTermProps) {
  const entry = GLOSSARY[slug]

  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={100}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span className="cursor-help border-b border-dotted border-dossier-evidenceTape/40 transition-colors hover:border-dossier-evidenceTape/80">
            {children}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={6}
            className="z-50 max-w-[260px] rounded border border-dossier-paperEdge bg-dossier-paper px-3 py-2.5 shadow-xl"
          >
            <p className="mb-1 font-case text-[11px] text-dossier-ink">{entry.title}</p>
            <p className="text-xs leading-snug text-dossier-ink/60">{entry.short}</p>
            <Link
              href={`/help#${slug}`}
              className="mt-1.5 block text-[10px] text-dossier-evidenceTape/60 transition-colors hover:text-dossier-evidenceTape"
            >
              Read more →
            </Link>
            <Tooltip.Arrow className="fill-dossier-paperEdge" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
