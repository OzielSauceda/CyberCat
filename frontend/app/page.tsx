"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, useState } from "react"
import { listDetections, listIncidents, type IncidentSummary } from "./lib/api"
import { connectStream, type StreamEvent } from "./lib/streaming"
import { useStream } from "./lib/useStream"
import { useSession } from "./lib/SessionContext"

// ─── Matrix Rain ─────────────────────────────────────────────────────────────

function MatrixRain({ opacity = 0.4 }: { opacity?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const CHARS = "アイウエオカキクケコABCDEF0123456789!@#$%<>{}[]|\\"
    const sz = 13
    let drops: number[] = []
    const resize = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
      drops = Array.from(
        { length: Math.floor(canvas.width / sz) },
        () => Math.random() * -(canvas.height / sz) * 2
      )
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    let id: number
    const tick = () => {
      ctx.fillStyle = "rgba(0,0,0,0.055)"
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      drops.forEach((y, i) => {
        ctx.fillStyle =
          Math.random() < 0.04
            ? "rgba(0,255,159,0.95)"
            : `rgba(0,${Math.floor(140 + Math.random() * 115)},${Math.floor(85 + Math.random() * 74)},${0.08 + Math.random() * 0.34})`
        ctx.font = `${sz}px monospace`
        ctx.fillText(CHARS[Math.floor(Math.random() * CHARS.length)], i * sz, y * sz)
        if (drops[i] * sz > canvas.height && Math.random() > 0.975) drops[i] = 0
        drops[i] += 0.5
      })
      id = requestAnimationFrame(tick)
    }
    tick()
    return () => { cancelAnimationFrame(id); ro.disconnect() }
  }, [])
  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 w-full h-full"
      style={{ opacity, mixBlendMode: "screen" }}
      aria-hidden
    />
  )
}

// ─── Scramble Title ───────────────────────────────────────────────────────────

const SCRAMBLE = "!<>-_\\/[]{}=+*^?#0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ∆∑≠≈∫"

function ScrambleTitle({ text }: { text: string }) {
  const [hovered, setHovered] = useState(false)
  const [chars, setChars] = useState(() =>
    text.split("").map((ch) => ({ ch, resolved: true }))
  )
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const iter = useRef(0)
  useEffect(() => {
    if (timer.current) clearInterval(timer.current)
    if (!hovered) {
      iter.current = 0
      setChars(text.split("").map((ch) => ({ ch, resolved: true })))
      return
    }
    iter.current = 0
    timer.current = setInterval(() => {
      const p = iter.current
      setChars(
        text.split("").map((ch, i) => {
          if (ch === " ") return { ch: " ", resolved: true }
          if (i < p) return { ch, resolved: true }
          return { ch: SCRAMBLE[Math.floor(Math.random() * SCRAMBLE.length)], resolved: false }
        })
      )
      iter.current += 0.38
      if (iter.current >= text.length) {
        clearInterval(timer.current!)
        setChars(text.split("").map((ch) => ({ ch, resolved: true })))
      }
    }, 30)
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [hovered, text])

  return (
    <h1
      className="font-case font-bold uppercase leading-none cursor-default select-none inline-block"
      style={{
        fontSize: "clamp(3.5rem,7vw,5.75rem)",
        letterSpacing: "0.07em",
        textShadow: "0 0 60px rgba(0,212,255,0.55), 0 0 140px rgba(0,212,255,0.18)",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {chars.map(({ ch, resolved }, i) => (
        <span
          key={i}
          className={resolved ? "rainbow-auto" : "text-cyber-green"}
          style={resolved ? undefined : { textShadow: "0 0 14px rgba(0,255,159,0.95)" }}
        >
          {ch}
        </span>
      ))}
    </h1>
  )
}

// ─── Threat Level ─────────────────────────────────────────────────────────────

type ThreatInfo = { label: string; color: string; bars: number; glow: string }

function getThreatLevel(incidents: IncidentSummary[]): ThreatInfo {
  const s = incidents.map((i) => i.severity)
  if (s.includes("critical")) return { label: "CRITICAL", color: "#ff2d55", bars: 5, glow: "rgba(255,45,85,0.4)"  }
  if (s.includes("high"))     return { label: "HIGH",     color: "#ff6b35", bars: 4, glow: "rgba(255,107,53,0.3)" }
  if (s.includes("medium"))   return { label: "MEDIUM",   color: "#fbbf24", bars: 3, glow: "rgba(251,191,36,0.25)"}
  if (incidents.length > 0)   return { label: "ELEVATED", color: "#00d4ff", bars: 2, glow: "rgba(0,212,255,0.25)" }
  return                              { label: "NOMINAL",  color: "#00ff9f", bars: 1, glow: "rgba(0,255,159,0.2)"  }
}

// ─── Hero Stat Cell ───────────────────────────────────────────────────────────

function HeroStat({
  label, value, accent, note,
}: {
  label: string; value: string | number; accent?: string; note?: string
}) {
  return (
    <div className="relative flex flex-col justify-between px-6 py-4 border-r border-dossier-paperEdge last:border-r-0 overflow-hidden">
      {accent && (
        <div
          className="absolute inset-x-0 top-0 h-px pointer-events-none"
          style={{ background: `linear-gradient(90deg, transparent, ${accent}70, transparent)` }}
        />
      )}
      <span
        className="font-mono text-[13px] uppercase tracking-widest"
        style={{ color: accent ? `${accent}cc` : "#e0eaf390" }}
      >
        {label}
      </span>
      <span
        className="font-case font-bold tabular-nums leading-none my-1"
        style={{
          fontSize: "2.5rem",
          color: accent ?? "#cdd6df",
          textShadow: accent ? `0 0 24px ${accent}55` : undefined,
        }}
      >
        {value}
      </span>
      {note && (
        <span className="font-mono text-[13px]" style={{ color: accent ? `${accent}bb` : "#e0eaf375" }}>
          {note}
        </span>
      )}
    </div>
  )
}

// ─── Active Case Row ──────────────────────────────────────────────────────────

const SEV: Record<string, string> = {
  critical: "#ff2d55",
  high:     "#ff6b35",
  medium:   "#fbbf24",
  low:      "#00d4ff",
  info:     "#cdd6df40",
}

function CaseRow({ incident }: { incident: IncidentSummary }) {
  const c = SEV[incident.severity] ?? "#cdd6df40"
  const isPriority = incident.severity === "critical" || incident.severity === "high"
  return (
    <Link
      href={`/incidents/${incident.id}`}
      className="group flex items-stretch overflow-hidden transition-all duration-150"
    >
      <div
        className="w-[3px] shrink-0 transition-all duration-150 group-hover:w-1"
        style={{ background: c, boxShadow: `0 0 8px ${c}80` }}
      />
      <div className="flex flex-1 items-center gap-3 px-3 py-2.5 border border-l-0 border-dossier-paperEdge bg-dossier-stamp group-hover:bg-dossier-paperEdge/40 group-hover:border-dossier-evidenceTape/20 transition-all duration-150">
        {/* Pulse dot */}
        <div className="relative shrink-0 w-1.5 h-1.5">
          {isPriority && (
            <div
              className="absolute inset-0 rounded-full animate-ping"
              style={{ background: c, opacity: 0.5 }}
            />
          )}
          <div className="absolute inset-0 rounded-full" style={{ background: c }} />
        </div>

        <span
          className="font-case text-xs font-bold uppercase tracking-wider shrink-0 w-9"
          style={{ color: c }}
        >
          {incident.severity.slice(0, 4).toUpperCase()}
        </span>

        <span className="flex-1 truncate text-xs font-medium text-dossier-ink/75 group-hover:text-dossier-ink transition-colors">
          {incident.title}
        </span>

        <span className="shrink-0 font-mono text-[13px] text-dossier-ink/20 group-hover:text-dossier-ink/45 transition-colors">
          #{incident.id.slice(-6).toUpperCase()}
        </span>

        <svg
          width="8" height="8" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.5"
          className="shrink-0 text-dossier-ink/15 group-hover:text-dossier-evidenceTape/60 transition-colors"
          aria-hidden
        >
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </div>
    </Link>
  )
}

// ─── Quick Nav Card ───────────────────────────────────────────────────────────

function NavCard({
  title, sub, href, primary,
}: {
  title: string; sub: string; href: string; primary?: boolean
}) {
  return (
    <Link
      href={href}
      className={[
        "group relative block overflow-hidden border transition-all duration-200 p-4",
        primary
          ? "border-dossier-evidenceTape/25 bg-dossier-evidenceTape/[0.04] hover:bg-dossier-evidenceTape/[0.08] hover:border-dossier-evidenceTape/50"
          : "border-dossier-paperEdge bg-dossier-stamp hover:border-dossier-paperEdge/80 hover:bg-dossier-paperEdge/30",
      ].join(" ")}
    >
      {primary && (
        <div
          className="absolute inset-x-0 top-0 h-px pointer-events-none"
          style={{ background: "linear-gradient(90deg, transparent, #00d4ff60, transparent)" }}
        />
      )}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
        style={{ background: "radial-gradient(ellipse at 10% 50%, rgba(0,212,255,0.05), transparent 65%)" }}
      />
      <p
        className={[
          "font-case text-[13px] font-bold uppercase tracking-widest mb-1 relative z-10 transition-colors",
          primary
            ? "text-dossier-evidenceTape"
            : "text-dossier-ink/70 group-hover:text-dossier-evidenceTape",
        ].join(" ")}
      >
        {title} <span className="opacity-50">→</span>
      </p>
      <p className="text-xs leading-relaxed text-dossier-ink/60 group-hover:text-dossier-ink/85 transition-colors relative z-10">
        {sub}
      </p>
    </Link>
  )
}

// ─── Live Event Ticker ────────────────────────────────────────────────────────

const SEV_COLOR: Record<string, string> = {
  critical: "#ff2d55",
  high:     "#ff6b35",
  medium:   "#fbbf24",
  low:      "#00d4ff",
  info:     "#cdd6df40",
}

interface TickerItem {
  id: string
  type: string
  src: string
  host: string
  flag: string
  flagColor: string
}

function toTickerItem(event: StreamEvent): TickerItem {
  const uid = `${event.type}-${Date.now()}-${Math.random()}`
  const short = (id: string) => `#${id.slice(-6).toUpperCase()}`
  switch (event.type) {
    case "incident.created":
      return { id: uid, type: "incident.created", src: short(event.data.incident_id), host: event.data.kind, flag: event.data.severity.toUpperCase(), flagColor: SEV_COLOR[event.data.severity] ?? "#cdd6df40" }
    case "incident.updated":
      return { id: uid, type: "incident.updated", src: short(event.data.incident_id), host: "", flag: event.data.change.toUpperCase(), flagColor: "#fbbf24" }
    case "incident.transitioned":
      return { id: uid, type: "incident.transitioned", src: short(event.data.incident_id), host: `${event.data.from_status}→${event.data.to_status}`, flag: "", flagColor: "" }
    case "detection.fired":
      return { id: uid, type: "detection.fired", src: event.data.rule_id, host: event.data.incident_id ? short(event.data.incident_id) : "", flag: event.data.severity?.toUpperCase() ?? "", flagColor: SEV_COLOR[event.data.severity ?? ""] ?? "" }
    case "action.proposed":
      return { id: uid, type: "action.proposed", src: event.data.kind, host: short(event.data.incident_id), flag: "PENDING", flagColor: "#fbbf24" }
    case "action.executed":
      return { id: uid, type: "action.executed", src: event.data.kind, host: short(event.data.incident_id), flag: event.data.result.toUpperCase(), flagColor: event.data.result === "success" ? "#00ff9f" : "#ff2d55" }
    case "action.reverted":
      return { id: uid, type: "action.reverted", src: event.data.kind, host: short(event.data.incident_id), flag: "REVERTED", flagColor: "#ff9500" }
    case "evidence.opened":
      return { id: uid, type: "evidence.opened", src: event.data.kind, host: short(event.data.incident_id), flag: "", flagColor: "" }
    case "evidence.collected":
      return { id: uid, type: "evidence.collected", src: short(event.data.evidence_request_id), host: short(event.data.incident_id), flag: "COLLECTED", flagColor: "#00ff9f" }
    case "evidence.dismissed":
      return { id: uid, type: "evidence.dismissed", src: short(event.data.evidence_request_id), host: short(event.data.incident_id), flag: "DISMISSED", flagColor: "#ff6b35" }
    default:
      return { id: uid, type: event.type, src: "", host: "", flag: "", flagColor: "" }
  }
}

function LiveTicker() {
  const [events, setEvents] = useState<TickerItem[]>([])

  useEffect(() => {
    const conn = connectStream({
      topics: ["incidents", "detections", "actions", "evidence"],
      onEvent(event) {
        if (event.type === "wazuh.status_changed") return
        setEvents(prev => [toTickerItem(event), ...prev].slice(0, 20))
      },
      onStatusChange() {},
    })
    return () => conn.close()
  }, [])

  const display = events.length > 0 ? [...events, ...events] : null
  const duration = Math.max(20, events.length * 3)

  return (
    <div
      className="flex overflow-hidden border border-dossier-paperEdge"
      style={{ height: "32px", background: "#030d1a" }}
    >
      {/* Fixed LIVE badge */}
      <div className="shrink-0 flex items-center gap-2 px-3 border-r border-dossier-paperEdge">
        <div className="relative w-1.5 h-1.5">
          <div className="absolute inset-0 rounded-full bg-dossier-evidenceTape animate-ping opacity-50" />
          <div className="absolute inset-0 rounded-full bg-dossier-evidenceTape" />
        </div>
        <span className="font-mono text-[13px] uppercase tracking-widest text-dossier-evidenceTape/40">LIVE</span>
      </div>

      {/* Scrolling area */}
      <div className="relative flex-1 overflow-hidden">
        <div
          className="absolute right-0 top-0 bottom-0 w-20 z-10 pointer-events-none"
          style={{ background: "linear-gradient(270deg, #030d1a, transparent)" }}
        />
        {display === null ? (
          <div className="flex items-center h-full px-4">
            <span className="font-mono text-[13px] tracking-widest" style={{ color: "#e0eaf330" }}>
              AWAITING EVENTS…
            </span>
          </div>
        ) : (
          <div
            className="flex items-center h-full"
            style={{ animation: `ticker-scroll ${duration}s linear infinite`, whiteSpace: "nowrap" }}
          >
            {display.map((ev, i) => (
              <span key={`${ev.id}-${i}`} className="font-mono text-xs flex items-center gap-2 px-5">
                <span style={{ color: "#00d4ff55" }}>{ev.type}</span>
                {ev.src && <span style={{ color: "#e0eaf355" }}>{ev.src}</span>}
                {ev.host && <span style={{ color: "#e0eaf335" }}>{ev.host}</span>}
                {ev.flag && (
                  <span
                    className="px-1 text-[11px] font-bold uppercase tracking-wider"
                    style={{
                      color: ev.flagColor,
                      border: `1px solid ${ev.flagColor}40`,
                      background: `${ev.flagColor}10`,
                    }}
                  >
                    {ev.flag}
                  </span>
                )}
                <span style={{ color: "#e0eaf315" }}>///</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const OPEN_STATUSES = "new,triaged,investigating,contained"

interface HomeData {
  openCount: number
  recentIncidents: IncidentSummary[]
  detectionsToday: number
  criticalCount: number
}

function todayISO() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.toISOString()
}

export default function HomePage() {
  const { user, status: authStatus } = useSession()

  const fetchIncidents = useCallback(
    () => listIncidents({ status: OPEN_STATUSES, limit: 5 }),
    []
  )
  const fetchDetections = useCallback(
    () => listDetections({ since: todayISO(), limit: 50 }),
    []
  )

  const { data: incData, error: incError } = useStream({
    topics: ["incidents"],
    fetcher: fetchIncidents,
    shouldRefetch: (e) =>
      e.type === "incident.created" ||
      e.type === "incident.updated" ||
      e.type === "incident.transitioned",
    fallbackPollMs: 30_000,
  })

  const { data: detData, error: detError } = useStream({
    topics: ["detections"],
    fetcher: fetchDetections,
    shouldRefetch: (e) => e.type === "detection.fired",
    fallbackPollMs: 30_000,
  })

  const incidents = incData?.items ?? []
  const data: HomeData | null =
    incData && detData
      ? {
          openCount: incidents.length,
          recentIncidents: incidents,
          detectionsToday: detData.items.length,
          criticalCount: incidents.filter((i) => i.severity === "critical").length,
        }
      : null
  const loadError = !!incError || !!detError

  const operatorHandle =
    user?.email ? user.email.split("@")[0] : authStatus === "loading" ? "…" : null
  const threat = getThreatLevel(data?.recentIncidents ?? [])
  const firstHref = data?.recentIncidents[0]
    ? `/incidents/${data.recentIncidents[0].id}`
    : "/incidents"
  const firstDesc = data?.recentIncidents[0]
    ? data.recentIncidents[0].title
    : data?.openCount === 0
    ? "No active cases — seed demo data to begin"
    : "Loading…"

  return (
    <div className="space-y-3 py-2">

      {/* ── HERO ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border border-dossier-paperEdge bg-dossier-stamp">
        {/* Corner brackets */}
        <div className="absolute top-3 right-3 w-5 h-5 border-t border-r border-dossier-evidenceTape/20 pointer-events-none" />
        <div className="absolute top-3 left-3 w-5 h-5 border-t border-l border-dossier-evidenceTape/10 pointer-events-none" />

        {/* Title block */}
        <div className="relative z-10 px-8 pt-7 pb-5">
          <div className="flex items-center gap-2 mb-3">
            <div
              className="w-1 h-3 bg-cyber-green"
              style={{ boxShadow: "0 0 6px #00ff9f" }}
            />
            <p
              className="font-mono text-xs uppercase tracking-[0.4em]"
              style={{ color: "#00ff9f65" }}
            >
              {operatorHandle ? `operator // ${operatorHandle}` : "threat intelligence platform"}
            </p>
            <span
              className="font-mono text-xs text-dossier-evidenceTape/35"
              style={{ animation: "cursor-blink 1.1s step-end infinite" }}
            >
              ▋
            </span>
          </div>

          <ScrambleTitle text="CYBERCAT" />

          <p
            className="mt-2 font-case font-semibold uppercase"
            style={{ fontSize: "0.9rem", letterSpacing: "0.22em", color: "#e0eaf378" }}
          >
            Automated Incident Response Platform
          </p>
        </div>

        {/* Stats bar */}
        <div className="relative z-10 grid grid-cols-4 border-t border-dossier-paperEdge">
          <HeroStat
            label="Open Cases"
            value={data === null ? "—" : data.openCount}
            accent={data?.openCount ? "#ff2d55" : undefined}
            note={data?.openCount ? "ACTIVE INVESTIGATIONS" : "NO ACTIVE CASES"}
          />
          <HeroStat
            label="Detections Today"
            value={data === null ? "—" : data.detectionsToday >= 50 ? "50+" : data.detectionsToday}
            accent={data?.detectionsToday ? "#fbbf24" : undefined}
            note="SINCE MIDNIGHT UTC"
          />
          <HeroStat
            label="Critical Priority"
            value={data === null ? "—" : data.criticalCount}
            accent={data?.criticalCount ? "#ff2d55" : undefined}
            note="REQUIRE IMMEDIATE ACTION"
          />

          {/* Threat level cell */}
          <div className="relative flex flex-col justify-between px-6 py-4 overflow-hidden">
            <div
              className="absolute inset-x-0 top-0 h-px pointer-events-none"
              style={{
                background: `linear-gradient(90deg, transparent, ${threat.color}60, transparent)`,
              }}
            />
            <span
              className="font-mono text-[13px] uppercase tracking-widest"
              style={{ color: `${threat.color}cc` }}
            >
              Threat Level
            </span>
            <div className="flex items-end gap-1 my-1.5">
              {[1, 2, 3, 4, 5].map((b) => (
                <div
                  key={b}
                  className="w-2 rounded-sm transition-all"
                  style={{
                    height: `${8 + b * 4}px`,
                    background: b <= threat.bars ? threat.color : "#0c1b2e",
                    boxShadow: b <= threat.bars ? `0 0 5px ${threat.color}70` : undefined,
                  }}
                />
              ))}
              <span
                className="ml-2 font-case font-bold text-sm tracking-widest"
                style={{
                  color: threat.color,
                  textShadow: `0 0 14px ${threat.glow}`,
                }}
              >
                {threat.label}
              </span>
            </div>
            {loadError ? (
              <span className="font-mono text-[13px] text-dossier-redaction/70">
                ⚠ BACKEND UNREACHABLE
              </span>
            ) : (
              <span className="font-mono text-[13px]" style={{ color: "#e0eaf360" }}>
                MITRE ATT&CK AWARE
              </span>
            )}
          </div>
        </div>

        {/* System status strip */}
        <div
          className="relative z-10 flex items-center border-t border-dossier-paperEdge/50"
          style={{ background: "rgba(0,0,0,0.25)" }}
        >
          <div className="flex items-center gap-2 px-4 py-1.5 border-r border-dossier-paperEdge/50">
            <div className="relative w-1.5 h-1.5">
              <div className="absolute inset-0 rounded-full bg-cyber-green animate-ping opacity-40" />
              <div className="absolute inset-0 rounded-full bg-cyber-green" />
            </div>
            <span
              className="font-mono text-[13px] uppercase tracking-widest"
              style={{ color: "#00ff9f99" }}
            >
              System Online
            </span>
          </div>
          {[
            "CyberCat v16.10",
            "Identity + Endpoint XDR",
            "ATT&CK correlation",
            "Wazuh opt-in available",
          ].map((item) => (
            <div
              key={item}
              className="flex items-center px-4 py-1.5 border-r border-dossier-paperEdge/40 last:border-r-0"
            >
              <span className="font-mono text-[13px]" style={{ color: "#e0eaf355" }}>
                {item}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ── LIVE TICKER ──────────────────────────────────────────────────── */}
      <LiveTicker />

      {/* ── MAIN CONTENT ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-3">

        {/* LEFT — Active intel + platform overview */}
        <div className="col-span-3 space-y-3">

          {/* Section header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-[2px] h-4 bg-dossier-evidenceTape" />
              <span className="font-case text-[13px] font-semibold uppercase tracking-[0.25em] text-dossier-evidenceTape">
                Active Intel
              </span>
              {data && data.openCount > 0 && (
                <span
                  className="font-mono text-[13px] px-1.5 py-0.5"
                  style={{
                    color: "#ff2d55",
                    border: "1px solid #ff2d5535",
                    background: "#ff2d5512",
                  }}
                >
                  {data.openCount} OPEN
                </span>
              )}
            </div>
            <Link
              href="/incidents"
              className="font-mono text-[13px] uppercase tracking-widest text-dossier-ink/45 hover:text-dossier-evidenceTape transition-colors"
            >
              All Cases →
            </Link>
          </div>

          {/* Cases list */}
          {data?.recentIncidents.length ? (
            <div className="space-y-1">
              {data.recentIncidents.map((inc) => (
                <CaseRow key={inc.id} incident={inc} />
              ))}
            </div>
          ) : (
            <div
              className="flex items-center justify-center border border-dossier-paperEdge py-7"
              style={{ background: "#030d1a" }}
            >
              <p className="font-mono text-xs tracking-widest" style={{ color: "#cdd6df18" }}>
                {data === null ? "LOADING INTEL…" : "NO ACTIVE CASES — SYSTEM NOMINAL"}
              </p>
            </div>
          )}

          {/* Platform mini-overview */}
          <div className="grid grid-cols-3 gap-2">
            {[
              {
                label: "Detection Engine",
                body: "Sigma + custom detectors. ATT&CK technique mapping on every signal. Confidence scoring.",
              },
              {
                label: "Correlation Layer",
                body: "Related signals grouped into cases. Full evidence chain retained. Explainable at every step.",
              },
              {
                label: "Response Policy",
                body: "Auto-safe → suggest-only → reversible → disruptive. Every action logged and auditable.",
              },
            ].map((c) => (
              <div
                key={c.label}
                className="p-3 border border-dossier-paperEdge bg-dossier-stamp relative overflow-hidden"
              >
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-dossier-evidenceTape/12 to-transparent pointer-events-none" />
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div className="w-1 h-1 rounded-full bg-dossier-evidenceTape/35" />
                  <p className="font-case text-xs font-bold uppercase tracking-widest text-dossier-ink/55">
                    {c.label}
                  </p>
                </div>
                <p className="text-xs leading-relaxed text-dossier-ink/60">{c.body}</p>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT — Quick nav + tour CTA */}
        <div className="col-span-2 space-y-2">
          <div className="flex items-center gap-2.5">
            <div className="w-[2px] h-4 bg-dossier-evidenceTape" />
            <span className="font-case text-[13px] font-semibold uppercase tracking-[0.25em] text-dossier-evidenceTape">
              Quick Access
            </span>
          </div>

          <NavCard
            title="Open Investigation"
            sub={firstDesc}
            href={firstHref}
            primary
          />
          <NavCard
            title="Detection Rules"
            sub="Rules that matched activity on your machine. When they fired and how confident."
            href="/detections"
          />
          <NavCard
            title="Response Actions"
            sub="Auto-run, pending approval, and rolled-back actions. Full audit trail."
            href="/actions"
          />
          <NavCard
            title="Lab Environment"
            sub="Sandboxed container for safe response action testing and observation."
            href="/lab"
          />

          {/* First-time CTA */}
          <div className="relative overflow-hidden border border-dossier-paperEdge bg-dossier-stamp p-4">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-dossier-evidenceTape/10 to-transparent pointer-events-none" />
            <p className="font-case text-[13px] font-bold uppercase tracking-wider text-dossier-ink/45 mb-1">
              First time here?
            </p>
            <p className="text-xs leading-relaxed text-dossier-ink/28 mb-3">
              Guided tour walks through a real case step by step.{" "}
              <Link
                href="/help#glossary"
                className="text-dossier-evidenceTape/45 hover:text-dossier-evidenceTape transition-colors"
              >
                Glossary →
              </Link>
            </p>
            <button
              type="button"
              onClick={() => {
                if (typeof window !== "undefined") {
                  localStorage.removeItem("cybercat:tour:completed")
                  window.location.assign("/incidents")
                }
              }}
              className="w-full py-2 font-case text-xs font-semibold uppercase tracking-widest border border-dossier-evidenceTape/20 text-dossier-evidenceTape/55 hover:border-dossier-evidenceTape/50 hover:text-dossier-evidenceTape hover:bg-dossier-evidenceTape/5 transition-all"
            >
              Take the Tour →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
