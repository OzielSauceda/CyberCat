"use client"

import { useEffect, useState } from "react"
import { getDemoStatus, wipeDemoData } from "../lib/api"

export default function DemoDataBanner() {
  const [active, setActive] = useState(false)
  const [wiping, setWiping] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    getDemoStatus()
      .then((s) => setActive(s.active))
      .catch(() => {})
  }, [])

  if (!active || dismissed) return null

  const handleWipe = async () => {
    setWiping(true)
    try {
      await wipeDemoData()
      setActive(false)
      // Full reload so all pages reflect the empty state
      window.location.assign("/")
    } catch {
      setWiping(false)
    }
  }

  return (
    <div className="flex items-center gap-3 border-b border-dossier-evidenceTape/20 bg-dossier-paperEdge/8 px-4 py-2">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-dossier-evidenceTape/60" />
      <p className="flex-1 text-xs text-zinc-400">
        You&apos;re looking at{" "}
        <span className="text-dossier-ink/80">demo data</span>
        {" "}— a simulated credential theft scenario so you can explore how CyberCat works.
      </p>
      <button
        onClick={handleWipe}
        disabled={wiping}
        className="shrink-0 text-xs text-dossier-evidenceTape/60 underline-offset-2 transition-colors hover:text-dossier-evidenceTape hover:underline disabled:opacity-40"
      >
        {wiping ? "Wiping…" : "Wipe and start fresh →"}
      </button>
      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss banner"
        className="shrink-0 text-zinc-700 transition-colors hover:text-zinc-500"
      >
        ✕
      </button>
    </div>
  )
}
