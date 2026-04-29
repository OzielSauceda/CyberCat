"use client"

import { useStream } from "../lib/useStream"

interface WazuhStatus {
  enabled: boolean
  reachable: boolean
  last_poll_at: string | null
  last_success_at: string | null
  lag_seconds: number | null
  events_ingested_total: number
  events_dropped_total: number
  last_error: string | null
}

async function fetchWazuhStatus(): Promise<WazuhStatus> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
  const res = await fetch(`${base}/v1/wazuh/status`, { cache: "no-store" })
  if (!res.ok) throw new Error(`wazuh status ${res.status}`)
  return res.json()
}

export default function WazuhBridgeBadge() {
  const { data } = useStream({
    topics: ["wazuh"],
    fetcher: fetchWazuhStatus,
    shouldRefetch: (e) => e.type === "wazuh.status_changed",
    fallbackPollMs: 15_000,
  })

  if (!data || !data.enabled) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-dossier-paperEdge px-2 py-0.5 text-[11px] font-mono tracking-wide text-dossier-ink/35">
        <span className="h-1.5 w-1.5 rounded-full bg-dossier-stamp/80" />
        WAZUH·OFF
      </span>
    )
  }

  if (data.reachable) {
    const label =
      data.lag_seconds !== null && data.lag_seconds < 30
        ? "WAZUH·LIVE"
        : data.last_success_at
        ? `WAZUH·${formatLag(data.lag_seconds)}s`
        : "WAZUH·LIVE"

    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-emerald-800/60 px-2 py-0.5 text-[11px] font-mono tracking-wide text-emerald-500/90">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        {label}
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-amber-800/60 px-2 py-0.5 text-[11px] font-mono tracking-wide text-amber-500/80 cursor-help"
      title={data.last_error ?? "Wazuh indexer unreachable"}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
      WAZUH·DOWN
    </span>
  )
}

function formatLag(seconds: number | null): number {
  return seconds ?? 0
}
