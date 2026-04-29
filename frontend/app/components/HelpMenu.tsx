"use client"

import Link from "next/link"
import * as Popover from "@radix-ui/react-popover"
import { TOUR_KEY, TOUR_RESTART_EVENT } from "./FirstRunTour"

function IconQuestion() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10"/>
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
      <circle cx="12" cy="17" r="0.5" fill="currentColor"/>
    </svg>
  )
}

export default function HelpMenu() {
  const clearTourFlag = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(TOUR_KEY)
      window.dispatchEvent(new CustomEvent(TOUR_RESTART_EVENT))
    }
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className="flex h-7 w-7 items-center justify-center rounded border border-dossier-paperEdge text-dossier-ink/40 transition-colors duration-150 hover:border-dossier-evidenceTape/60 hover:text-dossier-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-dossier-evidenceTape/50"
          aria-label="Help and case reference"
        >
          <IconQuestion />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-52 overflow-hidden rounded border border-dossier-paperEdge bg-dossier-paper shadow-2xl focus:outline-none"
        >
          {/* Header */}
          <div className="border-b border-dossier-paperEdge px-3 py-2">
            <p className="font-case text-[10px] uppercase tracking-[0.2em] text-dossier-evidenceTape/80">
              Case Reference
            </p>
          </div>

          {/* Items */}
          <div className="p-1">
            <Link
              href="/help"
              className="group flex items-center gap-2.5 rounded px-2.5 py-1.5 text-xs text-dossier-ink/70 transition-colors hover:bg-dossier-paperEdge hover:text-dossier-ink"
            >
              <span className="text-[11px] text-dossier-evidenceTape/35 group-hover:text-dossier-evidenceTape/65 select-none">?</span>
              What is this app?
            </Link>

            <Link
              href="/help#glossary"
              className="group flex items-center gap-2.5 rounded px-2.5 py-1.5 text-xs text-dossier-ink/70 transition-colors hover:bg-dossier-paperEdge hover:text-dossier-ink"
            >
              <span className="text-[11px] text-dossier-evidenceTape/35 group-hover:text-dossier-evidenceTape/65 select-none">≡</span>
              Open glossary
            </Link>

            <button
              onClick={clearTourFlag}
              className="group flex w-full items-center gap-2.5 rounded px-2.5 py-1.5 text-xs text-dossier-ink/70 transition-colors hover:bg-dossier-paperEdge hover:text-dossier-ink"
            >
              <span className="text-[11px] text-dossier-evidenceTape/35 group-hover:text-dossier-evidenceTape/65 select-none">▷</span>
              Restart tour
            </button>
          </div>

          {/* Footer */}
          <div className="border-t border-dossier-paperEdge px-3 py-2">
            <p className="text-[10px] text-dossier-ink/30">
              Runbook:{" "}
              <code className="font-mono text-dossier-evidenceTape/50">docs/runbook.md</code>
            </p>
          </div>

          <Popover.Arrow className="fill-dossier-paperEdge" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
