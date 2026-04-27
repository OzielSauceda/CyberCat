"use client"

import { useMemo, useRef, useState } from "react"
import type { IncidentDetail, TimelineEvent } from "../../lib/api"

type DetectionRef = IncidentDetail["detections"][number]

const LAYER: Record<string, { fill: string; label: string }> = {
  identity: { fill: "#6366f1", label: "Identity" },
  endpoint: { fill: "#84cc16", label: "Endpoint" },
  network:  { fill: "#06b6d4", label: "Network" },
  session:  { fill: "#10b981", label: "Session" },
  other:    { fill: "#71717a", label: "Other" },
}

function getLayer(kind: string): string {
  if (kind.startsWith("auth.")) return "identity"
  if (kind.startsWith("process.") || kind.startsWith("file.")) return "endpoint"
  if (kind.startsWith("network.")) return "network"
  if (kind.startsWith("session.")) return "session"
  return "other"
}

const ROLE_R: Record<string, number> = { trigger: 9, supporting: 6, context: 4 }

const SVG_W = 800
const SVG_H = 110
const PAD_L = 24
const PAD_R = 24
const BASELINE_Y = 62
const DETECT_Y = 18
const AXIS_Y = 90

function formatDelta(ms: number): string {
  const s = Math.round(ms / 1000)
  if (s < 60) return `+${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (rem === 0) return `+${m}m`
  if (m < 10) return `+${m}m${rem}s`
  return `+${m}m`
}

interface HoverInfo {
  lines: string[]
  color: string
}

export function IncidentTimelineViz({
  events,
  detections,
}: {
  events: TimelineEvent[]
  detections: DetectionRef[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<HoverInfo | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })

  const { scaledEvents, scaledDetections, ticks, presentLayers } = useMemo(() => {
    if (events.length === 0) {
      return { scaledEvents: [], scaledDetections: [], ticks: [], presentLayers: [] }
    }

    const eventTimes = events.map((e) => new Date(e.occurred_at).getTime())
    const detTimes = detections.map((d) => new Date(d.created_at).getTime())
    const allTimes = [...eventTimes, ...detTimes]

    const minMs = Math.min(...allTimes)
    const maxMs = Math.max(...allTimes)
    const span = Math.max(maxMs - minMs, 1000)

    const usableW = SVG_W - PAD_L - PAD_R
    const toX = (t: number) => PAD_L + ((t - minMs) / span) * usableW

    const scaledEvents = events.map((ev) => ({
      ...ev,
      svgX: toX(new Date(ev.occurred_at).getTime()),
      layer: getLayer(ev.kind),
      r: ROLE_R[ev.role_in_incident] ?? 5,
    }))

    const eventById = new Map(events.map((e) => [e.id, e]))

    const scaledDetections = detections.map((d) => {
      const triggeredEvent = eventById.get(d.event_id)
      return {
        ...d,
        svgX: toX(new Date(d.created_at).getTime()),
        triggerX: triggeredEvent
          ? toX(new Date(triggeredEvent.occurred_at).getTime())
          : null,
      }
    })

    const tickCount = 5
    const ticks = Array.from({ length: tickCount + 1 }).map((_, i) => ({
      svgX: PAD_L + (i / tickCount) * usableW,
      label: formatDelta((i / tickCount) * span),
    }))

    const layerSet = new Set(scaledEvents.map((e) => e.layer))
    const presentLayers = Array.from(layerSet)

    return { scaledEvents, scaledDetections, ticks, presentLayers }
  }, [events, detections])

  if (events.length === 0) return null

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Panel header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          Attack timeline
        </h2>
        <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
          {events.length} events
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          {presentLayers.map((layer) => (
            <span key={layer} className="flex items-center gap-1.5 text-[10px] text-zinc-500">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: LAYER[layer]?.fill }}
              />
              {LAYER[layer]?.label}
            </span>
          ))}
          {detections.length > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-zinc-500">
              <span className="text-amber-400 text-xs">▲</span>
              Detection
            </span>
          )}
        </div>
      </div>

      {/* SVG area */}
      <div
        ref={containerRef}
        className="relative px-3 pt-2 pb-1 select-none"
        onMouseMove={(e) => {
          const rect = containerRef.current?.getBoundingClientRect()
          if (rect) setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
        }}
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          width="100%"
          style={{ display: "block" }}
          aria-label="Incident attack timeline"
        >
          {/* Baseline */}
          <line
            x1={PAD_L} y1={BASELINE_Y}
            x2={SVG_W - PAD_R} y2={BASELINE_Y}
            stroke="#3f3f46" strokeWidth={1}
          />

          {/* Tick marks */}
          {ticks.map((tick, i) => (
            <g key={i}>
              <line
                x1={tick.svgX} y1={BASELINE_Y - 3}
                x2={tick.svgX} y2={BASELINE_Y + 3}
                stroke="#52525b" strokeWidth={1}
              />
              <text
                x={tick.svgX} y={AXIS_Y}
                textAnchor="middle"
                fontSize={9}
                fill="#52525b"
                fontFamily="ui-monospace, monospace"
              >
                {tick.label}
              </text>
            </g>
          ))}

          {/* Detection connectors + triangles */}
          {scaledDetections.map((d) => (
            <g key={d.id}>
              {d.triggerX !== null && (
                <line
                  x1={d.triggerX} y1={DETECT_Y + 10}
                  x2={d.triggerX} y2={BASELINE_Y}
                  stroke="#78350f" strokeWidth={1} strokeDasharray="3 2"
                />
              )}
              <g
                onMouseEnter={() =>
                  setHover({
                    color: "#f59e0b",
                    lines: [d.rule_id, `sev: ${d.severity_hint}`, `conf: ${d.confidence_hint}`],
                  })
                }
                onMouseLeave={() => setHover(null)}
                style={{ cursor: "pointer" }}
              >
                <polygon
                  points={`${d.svgX},${DETECT_Y} ${d.svgX - 7},${DETECT_Y + 12} ${d.svgX + 7},${DETECT_Y + 12}`}
                  fill="#78350f"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                />
              </g>
            </g>
          ))}

          {/* Event dots */}
          {scaledEvents.map((ev) => {
            const color = LAYER[ev.layer]?.fill ?? "#71717a"
            const isTrigger = ev.role_in_incident === "trigger"
            const isContext = ev.role_in_incident === "context"

            return (
              <g
                key={ev.id}
                onMouseEnter={() =>
                  setHover({
                    color,
                    lines: [
                      ev.kind,
                      new Date(ev.occurred_at).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      }),
                      ev.role_in_incident,
                      ev.source,
                    ],
                  })
                }
                onMouseLeave={() => setHover(null)}
                style={{ cursor: "default" }}
              >
                {isTrigger && (
                  <circle cx={ev.svgX} cy={BASELINE_Y} r={ev.r + 6} fill={color} opacity={0.14} />
                )}
                <circle
                  cx={ev.svgX}
                  cy={BASELINE_Y}
                  r={ev.r}
                  fill={isContext ? "transparent" : color}
                  stroke={color}
                  strokeWidth={isContext ? 1.5 : 0}
                  opacity={isContext ? 0.45 : 0.9}
                />
              </g>
            )
          })}
        </svg>

        {/* Tooltip */}
        {hover && (
          <div
            className="pointer-events-none absolute z-20 rounded border bg-zinc-950 px-2.5 py-1.5 text-xs shadow-xl"
            style={{
              left: mousePos.x > 600 ? mousePos.x - 148 : mousePos.x + 12,
              top: mousePos.y - 52,
              borderColor: hover.color,
            }}
          >
            {hover.lines.map((line, i) => (
              <p
                key={i}
                className={
                  i === 0
                    ? "font-mono font-semibold text-zinc-100"
                    : "font-mono text-zinc-500"
                }
              >
                {line}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
