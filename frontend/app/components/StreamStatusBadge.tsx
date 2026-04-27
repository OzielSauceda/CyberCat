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
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-700 px-2.5 py-0.5 text-xs text-amber-400">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
        Reconnecting
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-zinc-600 px-2.5 py-0.5 text-xs text-zinc-400"
      title="Live updates unavailable — polling for updates"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-zinc-500" />
      Polling
    </span>
  )
}
