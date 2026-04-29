"use client"

import { useEffect, useState } from "react"
import { connectStream, StreamStatus } from "../lib/streaming"

export default function StreamStatusBadge() {
  const [status, setStatus] = useState<StreamStatus | "idle">("idle")

  useEffect(() => {
    const conn = connectStream({
      topics: ["incidents", "detections", "actions", "evidence", "wazuh"],
      onEvent() {},
      onStatusChange(s) {
        setStatus(s)
      },
    })
    return () => conn.close()
  }, [])

  if (status === "idle" || status === "open") return null

  if (status === "reconnecting") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-amber-800/70 px-2 py-0.5 text-[11px] font-mono tracking-wide text-amber-500/90">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
        STREAM·RECONNECTING
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-dossier-paperEdge px-2 py-0.5 text-[11px] font-mono tracking-wide text-dossier-ink/50"
      title="Live updates unavailable — polling for updates"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-dossier-evidenceTape/40" />
      STREAM·POLLING
    </span>
  )
}
