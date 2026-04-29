// Layout helpers for the lane-based incident timeline visualization.
// Pure functions — no React, no DOM. Keeps the renderer focused on drawing.

import type { TimelineEvent } from "./api"

export type LayerKey = "identity" | "session" | "endpoint" | "network"

export interface LayerInfo {
  key: LayerKey
  label: string
  color: string
  // What kind of activity this lane represents, in plain English (tooltip).
  plain: string
}

// Lanes appear top-to-bottom in the order an attacker's story typically flows:
// who's logging in, what session they got, what programs they ran, where it
// reached out on the network.
export const LAYERS: readonly LayerInfo[] = [
  {
    key: "identity",
    label: "Identity",
    color: "#6366f1",
    plain: "Sign-in attempts and account activity.",
  },
  {
    key: "session",
    label: "Session",
    color: "#10b981",
    plain: "Login sessions opening and closing on a host.",
  },
  {
    key: "endpoint",
    label: "Endpoint",
    color: "#84cc16",
    plain: "Programs and files on the host.",
  },
  {
    key: "network",
    label: "Network",
    color: "#06b6d4",
    plain: "Network connections to and from the host.",
  },
] as const

export function eventLayer(kind: string): LayerKey {
  if (kind.startsWith("auth.")) return "identity"
  if (kind.startsWith("session.")) return "session"
  if (kind.startsWith("process.") || kind.startsWith("file.")) return "endpoint"
  if (kind.startsWith("network.")) return "network"
  return "endpoint"
}

export interface EntityThread {
  fromId: string
  toId: string
  entityId: string
}

// Build "red string" threads: for each entity, connect each pair of consecutive
// events that share it. Limits noise by skipping pairs in the same lane (the
// thread's job is to make cross-lane links visible, e.g. an auth event tied to
// a process event for the same user).
export function buildEntityThreads(events: TimelineEvent[]): EntityThread[] {
  const sorted = [...events].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
  )

  const byEntity = new Map<string, TimelineEvent[]>()
  for (const ev of sorted) {
    for (const eid of ev.entity_ids) {
      if (!byEntity.has(eid)) byEntity.set(eid, [])
      byEntity.get(eid)!.push(ev)
    }
  }

  const threads: EntityThread[] = []
  const seen = new Set<string>()
  for (const [entityId, evs] of byEntity) {
    if (evs.length < 2) continue
    for (let i = 1; i < evs.length; i++) {
      const a = evs[i - 1]
      const b = evs[i]
      if (eventLayer(a.kind) === eventLayer(b.kind)) continue
      const key = a.id < b.id ? `${a.id}|${b.id}` : `${b.id}|${a.id}`
      if (seen.has(key)) continue
      seen.add(key)
      threads.push({ fromId: a.id, toId: b.id, entityId })
    }
  }
  return threads
}

export interface TimeRange {
  minMs: number
  maxMs: number
  spanMs: number
}

export function timeRange(
  events: TimelineEvent[],
  detectionTimes: number[] = [],
): TimeRange | null {
  if (events.length === 0 && detectionTimes.length === 0) return null
  const all = [
    ...events.map((e) => new Date(e.occurred_at).getTime()),
    ...detectionTimes,
  ]
  const minMs = Math.min(...all)
  const maxMs = Math.max(...all)
  return { minMs, maxMs, spanMs: Math.max(maxMs - minMs, 1000) }
}

export function formatDelta(ms: number): string {
  const s = Math.round(ms / 1000)
  if (s < 60) return `+${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m < 10 && rem !== 0) return `+${m}m${rem}s`
  return `+${m}m`
}

// Tick marks at sensible intervals along the time axis.
export function buildTicks(range: TimeRange, count = 5): { offset: number; label: string }[] {
  return Array.from({ length: count + 1 }).map((_, i) => {
    const frac = i / count
    return {
      offset: frac,
      label: i === 0 ? "t₀" : i === count ? "now" : formatDelta(frac * range.spanMs),
    }
  })
}
