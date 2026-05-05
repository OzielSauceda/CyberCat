"use client"

import { useMemo, useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import type { IncidentDetail, TimelineEvent } from "../../lib/api"
import {
  EVENT_SOURCE_LABELS,
  INCIDENT_EVENT_ROLE_LABELS,
  eventKindLabel,
} from "../../lib/labels"
import {
  LAYERS,
  buildEntityThreads,
  buildTicks,
  eventLayer,
  timeRange,
  type LayerKey,
} from "../../lib/timelineLayout"

type DetectionRef = IncidentDetail["detections"][number]

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const LANE_HEIGHT = 64
const LANE_LABEL_W = 92
const PAD_TOP = 28
const PAD_BOTTOM = 36
const AXIS_HEIGHT = 22
const PLAYHEAD_DURATION = 1.2 // seconds

// ---------------------------------------------------------------------------
// Per-event placement
// ---------------------------------------------------------------------------

interface PlacedEvent {
  event: TimelineEvent
  layer: LayerKey
  xPct: number // percentage across the lane (0–100)
  fracDelay: number // 0–1 delay multiplier for the playhead reveal
  detection: DetectionRef | null
  isTrigger: boolean
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function IncidentTimelineViz({
  events,
  detections,
  splitMode = false,
  selectedEventIds,
  onToggleSplitEvent,
}: {
  events: TimelineEvent[]
  detections: DetectionRef[]
  // Phase 20 §C — split-mode props (optional; viz works fine without them)
  splitMode?: boolean
  selectedEventIds?: Set<string>
  onToggleSplitEvent?: (eventId: string) => void
}) {
  const reducedMotion = useReducedMotion() ?? false
  // Bumping this remounts the animated layer to replay the sweep on demand.
  const [replayKey, setReplayKey] = useState(0)
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  const range = useMemo(
    () => timeRange(events, detections.map((d) => new Date(d.created_at).getTime())),
    [events, detections],
  )

  // Group events by lane, keeping only lanes that actually have activity.
  const { activeLanes, placed, threads, ticks } = useMemo(() => {
    if (!range || events.length === 0) {
      return {
        activeLanes: [] as typeof LAYERS,
        placed: [] as PlacedEvent[],
        threads: [] as ReturnType<typeof buildEntityThreads>,
        ticks: [] as ReturnType<typeof buildTicks>,
      }
    }

    const detectionByEventId = new Map<string, DetectionRef>()
    for (const d of detections) {
      // Pick the highest-severity detection if multiple share an event.
      const existing = detectionByEventId.get(d.event_id)
      if (!existing || severityRank(d.severity_hint) > severityRank(existing.severity_hint)) {
        detectionByEventId.set(d.event_id, d)
      }
    }

    const lanesPresent = new Set<LayerKey>()
    const placed: PlacedEvent[] = events.map((ev) => {
      const layer = eventLayer(ev.kind)
      lanesPresent.add(layer)
      const t = new Date(ev.occurred_at).getTime()
      const frac = (t - range.minMs) / range.spanMs
      return {
        event: ev,
        layer,
        xPct: frac * 100,
        fracDelay: frac,
        detection: detectionByEventId.get(ev.id) ?? null,
        isTrigger: ev.role_in_incident === "trigger",
      }
    })

    const activeLanes = LAYERS.filter((l) => lanesPresent.has(l.key))
    const threads = buildEntityThreads(events).filter((th) => {
      // Only thread between events that actually rendered (defensive).
      return placed.some((p) => p.event.id === th.fromId) && placed.some((p) => p.event.id === th.toId)
    })

    return { activeLanes, placed, threads, ticks: buildTicks(range) }
  }, [events, detections, range])

  if (events.length === 0 || !range) return null

  const totalHeight =
    PAD_TOP + activeLanes.length * LANE_HEIGHT + PAD_BOTTOM + AXIS_HEIGHT

  const laneIndexFor = (layer: LayerKey) =>
    activeLanes.findIndex((l) => l.key === layer)

  const laneCenterY = (layer: LayerKey) => {
    const idx = laneIndexFor(layer)
    return PAD_TOP + idx * LANE_HEIGHT + LANE_HEIGHT / 2
  }

  const trackContentWidthPct = 100 // chip area is 100% of (parent − labels)

  // Resolve a placed event by id (for thread anchoring)
  const placedById = new Map(placed.map((p) => [p.event.id, p]))

  return (
    <div className="rounded-lg border border-dossier-paperEdge bg-dossier-paper shadow-dossier overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-dossier-paperEdge px-4 py-3">
        <span className="h-1.5 w-1.5 rounded-full bg-dossier-evidenceTape/60" />
        <h2 className="text-[11px] font-case font-semibold uppercase tracking-widest text-dossier-evidenceTape">
          The reel
        </h2>
        <span className="rounded border border-dossier-paperEdge bg-dossier-stamp px-2 py-0.5 font-mono text-[10px] text-dossier-ink/50">
          {events.length}
        </span>
        <span className="hidden sm:inline-block max-w-md truncate text-[11px] leading-snug text-dossier-ink/45">
          Each lane is one kind of activity. The playhead sweeps left to right as the case unfolds.
        </span>
        <button
          type="button"
          onClick={() => setReplayKey((k) => k + 1)}
          className="ml-auto inline-flex items-center gap-1.5 rounded border border-dossier-paperEdge bg-dossier-stamp px-2.5 py-1 font-case text-[10px] uppercase tracking-widest text-dossier-ink/55 transition-colors hover:border-dossier-evidenceTape/40 hover:text-dossier-evidenceTape"
          aria-label="Replay timeline animation"
        >
          <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <path d="M8 5v14l11-7z" />
          </svg>
          Replay
        </button>
      </div>

      {/* Track */}
      <div
        className="relative px-2 py-2"
        style={{
          backgroundImage:
            "radial-gradient(circle at 25% 25%, rgba(0,212,255,0.025), transparent 60%)",
        }}
      >
        <div
          className="relative"
          style={{ height: totalHeight, paddingLeft: LANE_LABEL_W }}
        >
          {/* Lane labels */}
          {activeLanes.map((lane, idx) => {
            const y = PAD_TOP + idx * LANE_HEIGHT
            return (
              <motion.div
                key={`label-${lane.key}-${replayKey}`}
                className="absolute left-0 flex items-center"
                style={{ top: y, height: LANE_HEIGHT, width: LANE_LABEL_W }}
                initial={reducedMotion ? false : { opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: idx * 0.06 }}
              >
                <div
                  className="flex flex-col gap-1 pr-2"
                  title={lane.plain}
                >
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{
                        backgroundColor: lane.color,
                        boxShadow: `0 0 6px ${lane.color}99`,
                      }}
                    />
                    <span className="font-case text-[10px] font-bold uppercase tracking-widest text-dossier-ink/70">
                      {lane.label}
                    </span>
                  </span>
                </div>
              </motion.div>
            )
          })}

          {/* Lane baselines (SVG layer) */}
          <svg
            className="absolute inset-0 pointer-events-none"
            style={{ left: LANE_LABEL_W, width: `calc(100% - ${LANE_LABEL_W}px)`, height: totalHeight }}
            preserveAspectRatio="none"
          >
            <defs>
              {/* Slight imperfection on the rules — pen on paper */}
              <filter id="reel-rough" x="0" y="-50%" width="100%" height="200%">
                <feTurbulence baseFrequency="0.85" numOctaves="2" seed="7" />
                <feDisplacementMap in="SourceGraphic" scale="0.5" />
              </filter>
            </defs>
            {activeLanes.map((lane, idx) => {
              const y = PAD_TOP + idx * LANE_HEIGHT + LANE_HEIGHT / 2
              return (
                <motion.line
                  key={`baseline-${lane.key}-${replayKey}`}
                  x1="0"
                  x2="100%"
                  y1={y}
                  y2={y}
                  stroke={lane.color}
                  strokeOpacity={0.25}
                  strokeWidth={1}
                  strokeDasharray="2 4"
                  filter="url(#reel-rough)"
                  initial={reducedMotion ? false : { pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.5, delay: 0.15 + idx * 0.05 }}
                />
              )
            })}

            {/* Red-string entity threads */}
            {threads.map((th) => {
              const a = placedById.get(th.fromId)
              const b = placedById.get(th.toId)
              if (!a || !b) return null
              const ax = `${a.xPct}%`
              const ay = laneCenterY(a.layer)
              const bx = `${b.xPct}%`
              const by = laneCenterY(b.layer)
              const isHovered = hoveredId === th.fromId || hoveredId === th.toId
              const opacity = hoveredId == null ? 0.18 : isHovered ? 0.85 : 0.05
              // Curve so threads don't crash through other lanes' chips
              const midY = (ay + by) / 2
              const path = `M ${ax} ${ay} Q ${ax} ${midY}, ${bx} ${by}`
              return (
                <motion.path
                  key={`thread-${th.fromId}-${th.toId}-${replayKey}`}
                  d={path}
                  fill="none"
                  stroke="#ff2d55"
                  strokeWidth={isHovered ? 1.4 : 1}
                  strokeDasharray="3 3"
                  strokeLinecap="round"
                  initial={reducedMotion ? false : { pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity }}
                  transition={{
                    pathLength: { duration: 0.45, delay: PLAYHEAD_DURATION + 0.05 },
                    opacity: { duration: 0.25 },
                  }}
                  style={{ filter: "drop-shadow(0 0 3px rgba(255,45,85,0.45))" }}
                />
              )
            })}

            {/* Playhead — sweeps from left to right on mount */}
            <motion.line
              key={`playhead-${replayKey}`}
              y1={PAD_TOP - 6}
              y2={PAD_TOP + activeLanes.length * LANE_HEIGHT + 4}
              stroke="#00d4ff"
              strokeWidth={1.5}
              strokeOpacity={0.85}
              initial={reducedMotion ? { x1: "100%", x2: "100%" } : { x1: 0, x2: 0 }}
              animate={{ x1: "100%", x2: "100%" }}
              transition={{ duration: PLAYHEAD_DURATION, ease: "easeInOut" }}
              style={{ filter: "drop-shadow(0 0 5px rgba(0,212,255,0.7))" }}
            />
          </svg>

          {/* Event chips (HTML over SVG so we get text rendering + Tailwind) */}
          <div
            className="absolute inset-0"
            style={{ left: LANE_LABEL_W, width: `calc(100% - ${LANE_LABEL_W}px)` }}
          >
            {placed.map((p) => {
              const lane = LAYERS.find((l) => l.key === p.layer)!
              const y = laneCenterY(p.layer)
              const delay = reducedMotion
                ? 0
                : 0.15 + p.fracDelay * PLAYHEAD_DURATION
              return (
                <EventChip
                  key={`${p.event.id}-${replayKey}`}
                  placed={p}
                  laneColor={lane.color}
                  y={y}
                  delay={delay}
                  reducedMotion={reducedMotion}
                  hovered={hoveredId === p.event.id}
                  onHover={(id) => setHoveredId(id)}
                  splitMode={splitMode}
                  selected={selectedEventIds?.has(p.event.id) ?? false}
                  onToggleSplit={onToggleSplitEvent}
                />
              )
            })}
          </div>

          {/* Time axis */}
          <div
            className="absolute"
            style={{
              left: LANE_LABEL_W,
              right: 0,
              top: PAD_TOP + activeLanes.length * LANE_HEIGHT + 12,
              height: AXIS_HEIGHT,
            }}
          >
            <div className="relative h-full">
              {ticks.map((t, i) => (
                <div
                  key={i}
                  className="absolute top-0 -translate-x-1/2 text-center"
                  style={{ left: `${t.offset * 100}%` }}
                >
                  <div className="mx-auto h-1.5 w-px bg-dossier-ink/20" />
                  <span className="mt-0.5 inline-block font-mono text-[10px] text-dossier-ink/35">
                    {t.label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Footer legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-dossier-paperEdge px-4 py-2 text-[10px] text-dossier-ink/45">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: "#00d4ff", boxShadow: "0 0 6px rgba(0,212,255,0.7)" }}
          />
          Trigger — what opened the case
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-0 w-0"
            style={{
              borderLeft: "5px solid transparent",
              borderRight: "5px solid transparent",
              borderBottom: "8px solid #f59e0b",
            }}
          />
          Detection rule matched
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-px w-5 bg-dossier-redaction/70"
            style={{ borderTop: "1px dashed #ff2d55" }}
          />
          Same user / same machine
        </span>
        <span className="ml-auto font-mono text-[10px] text-dossier-ink/30">
          {events.length} events · {detections.length} detections
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Event chip
// ---------------------------------------------------------------------------

interface EventChipProps {
  placed: PlacedEvent
  laneColor: string
  y: number
  delay: number
  reducedMotion: boolean
  hovered: boolean
  onHover: (id: string | null) => void
  splitMode?: boolean
  selected?: boolean
  onToggleSplit?: (eventId: string) => void
}

function EventChip({
  placed,
  laneColor,
  y,
  delay,
  reducedMotion,
  hovered,
  onHover,
  splitMode = false,
  selected = false,
  onToggleSplit,
}: EventChipProps) {
  const { event: ev, isTrigger, detection } = placed
  const role = ev.role_in_incident
  const kindEntry = eventKindLabel(ev.kind)
  const sourceEntry = EVENT_SOURCE_LABELS[ev.source]
  const roleEntry = INCIDENT_EVENT_ROLE_LABELS[role]

  // Decide rendering style:
  //   trigger        → big chip ABOVE the baseline + glowing dot + detection stamp
  //   has detection  → labeled chip ABOVE + amber stamp
  //   supporting     → small chip BELOW the baseline
  //   context        → tiny dot ON the baseline (label on hover only)
  const showLabelInline = isTrigger || detection != null
  const placeAbove = isTrigger || detection != null
  const labelText = kindEntry.label
  const hostOrTarget = previewSubject(ev)

  return (
    <motion.div
      className="absolute group"
      style={{ left: `${placed.xPct}%`, top: y, transform: "translate(-50%, -50%)" }}
      initial={reducedMotion ? false : { opacity: 0, scale: 0.4 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.35, delay, ease: [0.2, 1.4, 0.4, 1] }}
      onMouseEnter={() => onHover(ev.id)}
      onMouseLeave={() => onHover(null)}
    >
      {/* Detection stamp — sits above the chip */}
      {detection && (
        <motion.div
          className="absolute left-1/2 -translate-x-1/2"
          style={{ bottom: 28 }}
          initial={reducedMotion ? false : { opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: delay + 0.12 }}
        >
          <div className="flex flex-col items-center">
            <span
              className="font-case text-[8px] font-bold uppercase tracking-widest text-amber-400/80 mb-0.5"
              style={{ textShadow: "0 0 4px rgba(245,158,11,0.5)" }}
            >
              rule matched
            </span>
            <span
              className="block h-0 w-0"
              style={{
                borderLeft: "6px solid transparent",
                borderRight: "6px solid transparent",
                borderBottom: "9px solid #f59e0b",
                filter: "drop-shadow(0 0 4px rgba(245,158,11,0.55))",
              }}
              aria-hidden
            />
          </div>
        </motion.div>
      )}

      {/* Inline label (above for triggers/detections, below for supporting) */}
      {showLabelInline && (
        <div
          className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap"
          style={placeAbove ? { bottom: 14 } : { top: 14 }}
        >
          <div className="rounded border border-dossier-paperEdge bg-dossier-paper/95 px-1.5 py-0.5 shadow-sm backdrop-blur-sm">
            <span className="font-case text-[10px] font-semibold uppercase tracking-wider text-dossier-ink/85">
              {labelText}
            </span>
            {hostOrTarget && (
              <span className="ml-1.5 font-mono text-[9px] text-dossier-ink/45">
                {hostOrTarget}
              </span>
            )}
          </div>
        </div>
      )}

      {/* The dot itself */}
      <span className="relative block">
        {isTrigger && !reducedMotion && !splitMode && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{
              background: laneColor,
              opacity: 0.35,
            }}
            animate={{ scale: [1, 2.2, 1], opacity: [0.4, 0, 0.4] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
        <span
          className={`relative block rounded-full transition-all ${
            isTrigger
              ? "h-3 w-3"
              : detection
              ? "h-2.5 w-2.5"
              : role === "supporting"
              ? "h-2 w-2"
              : "h-1.5 w-1.5"
          }`}
          style={{
            background:
              role === "context" ? "transparent" : laneColor,
            border: role === "context" ? `1.5px solid ${laneColor}aa` : "none",
            boxShadow: isTrigger
              ? `0 0 10px ${laneColor}, 0 0 16px ${laneColor}77`
              : detection
              ? `0 0 6px ${laneColor}99`
              : "none",
            outline: hovered ? `2px solid ${laneColor}` : "none",
            outlineOffset: 2,
          }}
        />
        {/* Phase 20 §C — split-mode checkbox overlay; takes priority over the
            dot's own click target so the operator can freely toggle without
            triggering hover-only behaviors. */}
        {splitMode && onToggleSplit && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onToggleSplit(ev.id) }}
            aria-pressed={selected}
            aria-label={selected ? "Unselect event for split" : "Select event for split"}
            className={`absolute -inset-1.5 z-20 rounded-full border-2 transition-all ${
              selected
                ? "border-cyber-orange bg-cyber-orange/30 shadow-[0_0_14px_rgba(255,107,53,0.55)]"
                : "border-dossier-evidenceTape/55 bg-dossier-stamp/70 hover:border-dossier-evidenceTape hover:shadow-[0_0_12px_rgba(0,212,255,0.35)]"
            }`}
          >
            {selected && (
              <svg
                className="absolute inset-0 m-auto h-3 w-3 text-cyber-orange"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M3 8l3.5 3.5L13 5" />
              </svg>
            )}
          </button>
        )}
      </span>

      {/* Hover tooltip — full detail, single source of truth */}
      {hovered && (
        <div
          className="pointer-events-none absolute left-1/2 z-30 -translate-x-1/2 whitespace-nowrap rounded border bg-dossier-paper px-2.5 py-1.5 shadow-xl"
          style={{
            top: -68,
            borderColor: laneColor,
          }}
        >
          <p className="font-case text-[11px] font-semibold text-dossier-ink">
            {kindEntry.label}
          </p>
          <p className="font-mono text-[9px] text-dossier-ink/40 mt-0.5">
            {ev.kind} · {sourceEntry.label}
          </p>
          <p className="font-mono text-[10px] text-dossier-ink/55 mt-0.5">
            {new Date(ev.occurred_at).toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </p>
          <p className="font-mono text-[10px] mt-1" style={{ color: laneColor }}>
            {roleEntry.label}
          </p>
          {detection && (
            <p className="font-mono text-[10px] text-amber-400 mt-0.5">
              ▲ {detection.rule_id}
            </p>
          )}
        </div>
      )}
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function severityRank(s: string): number {
  return ({ info: 0, low: 1, medium: 2, high: 3, critical: 4 } as Record<string, number>)[s] ?? 0
}

function previewSubject(ev: TimelineEvent): string {
  const n = ev.normalized
  const s = (k: string) => (typeof n[k] === "string" ? (n[k] as string) : "")
  switch (ev.kind) {
    case "auth.failed":
    case "auth.succeeded": {
      const u = s("user")
      const ip = s("source_ip")
      return [u, ip].filter(Boolean).join(" · ")
    }
    case "session.started":
    case "session.ended":
      return [s("user"), s("host")].filter(Boolean).join(" → ")
    case "process.created":
    case "process.exited": {
      const img = s("image").split(/[\\/]/).pop() ?? ""
      return img
    }
    case "file.created":
    case "file.modified":
      return s("path") || s("name")
    case "network.connection":
      return [s("dst_ip"), s("dst_port")].filter(Boolean).join(":")
    default:
      return ""
  }
}
