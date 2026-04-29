"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { listDetections, listIncidents, type IncidentSummary } from "./lib/api"
import { useSession } from "./lib/SessionContext"

// ---------------------------------------------------------------------------
// Matrix Rain canvas background
// ---------------------------------------------------------------------------

function MatrixRain() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const KATAKANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
    const ASCII = "ABCDEF0123456789!@#$%<>{}[]|\\"
    const CHARS = KATAKANA + ASCII
    const fontSize = 13
    let drops: number[] = []

    function resize() {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
      drops = Array.from(
        { length: Math.floor(canvas.width / fontSize) },
        () => Math.random() * -(canvas.height / fontSize) * 2
      )
    }

    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    let animId: number
    function tick() {
      ctx.fillStyle = "rgba(0,0,0,0.055)"
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      drops.forEach((y, i) => {
        const isHead = Math.random() < 0.04
        if (isHead) {
          ctx.fillStyle = "rgba(180,255,180,0.92)"
        } else {
          const g = Math.floor(130 + Math.random() * 125)
          ctx.fillStyle = `rgba(0,${g},28,${0.1 + Math.random() * 0.38})`
        }
        ctx.font = `${fontSize}px monospace`
        ctx.fillText(CHARS[Math.floor(Math.random() * CHARS.length)], i * fontSize, y * fontSize)

        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0
        drops[i] += 0.5
      })

      animId = requestAnimationFrame(tick)
    }

    tick()
    return () => { cancelAnimationFrame(animId); ro.disconnect() }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 w-full h-full"
      style={{ opacity: 0.52, mixBlendMode: "screen" }}
      aria-hidden
    />
  )
}

// ---------------------------------------------------------------------------
// Scramble title hover effect
// ---------------------------------------------------------------------------

const SCRAMBLE = "!<>-_\\/[]{}=+*^?#0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ∆∑≠≈∫"

function ScrambleTitle({ text }: { text: string }) {
  const [hovered, setHovered] = useState(false)
  const [chars, setChars] = useState<Array<{ ch: string; resolved: boolean }>>(
    () => text.split("").map((ch) => ({ ch, resolved: true }))
  )
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const iterRef = useRef(0)

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)

    if (!hovered) {
      iterRef.current = 0
      setChars(text.split("").map((ch) => ({ ch, resolved: true })))
      return
    }

    iterRef.current = 0
    timerRef.current = setInterval(() => {
      const progress = iterRef.current
      setChars(
        text.split("").map((ch, i) => {
          if (ch === " ") return { ch: " ", resolved: true }
          if (i < progress) return { ch, resolved: true }
          return { ch: SCRAMBLE[Math.floor(Math.random() * SCRAMBLE.length)], resolved: false }
        })
      )
      iterRef.current += 0.38
      if (iterRef.current >= text.length) {
        clearInterval(timerRef.current!)
        setChars(text.split("").map((ch) => ({ ch, resolved: true })))
      }
    }, 30)

    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [hovered, text])

  return (
    <h1
      className="font-case text-5xl font-bold uppercase tracking-widest cursor-default select-none"
      style={{ textShadow: "0 0 40px rgba(0,212,255,0.35)" }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {chars.map(({ ch, resolved }, i) => (
        <span
          key={i}
          className={resolved ? "text-dossier-evidenceTape" : "text-green-400"}
          style={resolved ? undefined : { textShadow: "0 0 14px rgba(74,222,128,0.95)" }}
        >
          {ch}
        </span>
      ))}
    </h1>
  )
}

// ---------------------------------------------------------------------------
// Severity accent colors
// ---------------------------------------------------------------------------

const severityNeon: Record<string, string> = {
  critical: "text-dossier-redaction",
  high:     "text-cyber-orange",
  medium:   "text-cyber-yellow",
  low:      "text-sky-400",
  info:     "text-dossier-ink/50",
}

const severityBg: Record<string, string> = {
  critical: "border-l-dossier-redaction",
  high:     "border-l-cyber-orange",
  medium:   "border-l-cyber-yellow",
  low:      "border-l-sky-400",
  info:     "border-l-dossier-paperEdge",
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatPill({ label, value, neon, animateCount }: {
  label: string
  value: string
  neon?: boolean
  animateCount?: number
}) {
  const [counted, setCounted] = useState<number | null>(null)

  useEffect(() => {
    if (animateCount == null || animateCount === 0) { setCounted(null); return }
    setCounted(0)
    const steps = 26
    let i = 0
    const id = setInterval(() => {
      i++
      if (i >= steps) { clearInterval(id); setCounted(null) }
      else setCounted(Math.round((animateCount * i) / steps))
    }, 700 / steps)
    return () => clearInterval(id)
  }, [animateCount])

  return (
    <div className="flex flex-col items-center gap-1">
      <span
        className={`font-case text-3xl font-bold tabular-nums ${
          neon ? "text-dossier-evidenceTape drop-shadow-[0_0_12px_rgba(0,212,255,0.5)]" : "text-dossier-ink"
        }`}
      >
        {counted !== null ? counted : value}
      </span>
      <span className="font-case text-[10px] uppercase tracking-[0.2em] text-dossier-ink/40">{label}</span>
    </div>
  )
}

function ActionCard({
  title,
  sub,
  href,
  accent,
}: {
  title: string
  sub: string
  href: string
  accent?: boolean
}) {
  return (
    <Link
      href={href}
      className={`group relative block overflow-hidden rounded-lg border p-5 transition-all duration-200 ${
        accent
          ? "border-dossier-evidenceTape/30 bg-dossier-evidenceTape/5 hover:bg-dossier-evidenceTape/10 hover:border-dossier-evidenceTape/60"
          : "border-dossier-paperEdge bg-dossier-paper hover:border-dossier-evidenceTape/20 hover:bg-dossier-paperEdge/60"
      }`}
    >
      {accent && (
        <span className="pointer-events-none absolute inset-0 rounded-lg opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{ boxShadow: "inset 0 0 30px rgba(0,212,255,0.04)" }} />
      )}
      <p className={`font-case text-sm font-semibold uppercase tracking-wider mb-1.5 ${
        accent ? "text-dossier-evidenceTape" : "text-dossier-ink"
      } group-hover:text-dossier-evidenceTape transition-colors`}>
        {title} →
      </p>
      <p className="text-xs leading-relaxed text-dossier-ink/45">{sub}</p>
    </Link>
  )
}

function RecentIncidentRow({ incident }: { incident: IncidentSummary }) {
  const sev = incident.severity as string
  return (
    <Link
      href={`/incidents/${incident.id}`}
      className={`group flex items-center gap-3 rounded border-l-2 border border-dossier-paperEdge bg-dossier-paper px-3 py-2.5 transition-colors hover:bg-dossier-paperEdge/60 ${severityBg[sev] ?? "border-l-dossier-paperEdge"}`}
    >
      <span className={`shrink-0 font-case text-[10px] font-bold uppercase tracking-wider ${severityNeon[sev] ?? "text-dossier-ink/50"}`}>
        {incident.severity.toUpperCase().slice(0, 4)}
      </span>
      <span className="flex-1 truncate text-xs text-dossier-ink group-hover:text-dossier-evidenceTape transition-colors">
        {incident.title}
      </span>
      <span className="shrink-0 font-mono text-[10px] text-dossier-ink/30">
        #{incident.id.slice(-6).toUpperCase()}
      </span>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const OPEN_STATUSES = "new,triaged,investigating,contained"

interface HomeData {
  openCount: number
  recentIncidents: IncidentSummary[]
  detectionsToday: number
}

function todayISO() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.toISOString()
}

export default function HomePage() {
  const { user, status: authStatus } = useSession()
  const [data, setData] = useState<HomeData | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const [incRes, detRes] = await Promise.allSettled([
          listIncidents({ status: OPEN_STATUSES, limit: 5 }),
          listDetections({ since: todayISO(), limit: 50 }),
        ])
        setData({
          openCount: incRes.status === "fulfilled" ? incRes.value.items.length : 0,
          recentIncidents: incRes.status === "fulfilled" ? incRes.value.items : [],
          detectionsToday: detRes.status === "fulfilled" ? detRes.value.items.length : 0,
        })
      } catch {
        setLoadError(true)
      }
    }
    load()
  }, [])

  const operatorHandle =
    user?.email ? user.email.split("@")[0] : authStatus === "loading" ? "…" : null

  const firstHref =
    data?.recentIncidents[0] ? `/incidents/${data.recentIncidents[0].id}` : "/incidents"

  const firstDesc =
    data?.recentIncidents[0]
      ? data.recentIncidents[0].title
      : data?.openCount === 0
      ? "No active cases — seed demo data to begin"
      : "Loading…"

  return (
    <div className="space-y-10 py-4">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-xl border border-dossier-paperEdge bg-dossier-stamp px-8 py-12">
        <MatrixRain />

        {/* Scanline sweep */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          <div
            className="absolute left-0 right-0 h-px"
            style={{
              background: "linear-gradient(90deg, transparent, rgba(0,212,255,0.07), rgba(0,212,255,0.38), rgba(0,212,255,0.07), transparent)",
              animation: "scanline-sweep 5s ease-in-out infinite",
              animationDelay: "1.2s",
            }}
          />
        </div>

        {/* content sits above the matrix bg */}
        <div className="relative z-10">
          <p className="mb-1 font-case text-[10px] uppercase tracking-[0.4em] text-dossier-evidenceTape/60">
            {operatorHandle ? `operator // ${operatorHandle}` : "threat intelligence platform"}
          </p>
          <ScrambleTitle text="CYBERCAT" />
          <p className="mt-1 font-case text-sm font-semibold uppercase tracking-[0.25em] text-dossier-ink/50">
            Automated Incident Response Platform
          </p>

          {/* Live stats */}
          <div className="mt-8 flex flex-wrap gap-10">
            <StatPill
              label="Open Cases"
              value={data === null ? "—" : String(data.openCount)}
              neon={!!data?.openCount}
              animateCount={data?.openCount}
            />
            <StatPill
              label="Detections Today"
              value={data === null ? "—" : data.detectionsToday >= 50 ? "50+" : String(data.detectionsToday)}
              neon={!!data?.detectionsToday}
              animateCount={data == null ? undefined : Math.min(data.detectionsToday, 50)}
            />
            {loadError && (
              <p className="self-center font-mono text-xs text-dossier-redaction/80">
                ⚠ backend unreachable — run ./start.sh
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ── Get started ──────────────────────────────────────────────────── */}
      <section>
        <p className="mb-3 font-case text-[10px] uppercase tracking-[0.3em] text-dossier-evidenceTape/45">
          Get Started
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <ActionCard
            title="Open Investigation"
            sub={firstDesc}
            href={firstHref}
            accent
          />
          <ActionCard
            title="Detection Rules"
            sub="See which rules matched activity on your machine, when they fired, and how confident the match was."
            href="/detections"
          />
          <ActionCard
            title="Response Actions"
            sub="Track every automated and manual action — what ran, what's waiting, and what was rolled back."
            href="/actions"
          />
        </div>
      </section>

      {/* ── Recent incidents ─────────────────────────────────────────────── */}
      {data && data.recentIncidents.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <p className="font-case text-[10px] uppercase tracking-[0.3em] text-dossier-evidenceTape/45">
              Active Cases
            </p>
            <Link
              href="/incidents"
              className="font-case text-[10px] uppercase tracking-[0.15em] text-dossier-ink/35 transition-colors hover:text-dossier-evidenceTape"
            >
              All cases →
            </Link>
          </div>
          <div className="space-y-1.5">
            {data.recentIncidents.map((inc) => (
              <RecentIncidentRow key={inc.id} incident={inc} />
            ))}
          </div>
        </section>
      )}

      {/* ── Platform overview ────────────────────────────────────────────── */}
      <section>
        <p className="mb-3 font-case text-[10px] uppercase tracking-[0.3em] text-dossier-evidenceTape/45">
          Platform Overview
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              title: "What CyberCat does",
              body: "Watches login and system activity, groups suspicious events into a case, shows you the full picture of what happened, and helps you take action — all from one machine.",
            },
            {
              title: "What it isn't",
              body: "Not a log aggregator, not an antivirus, not a Wazuh skin. Those tools feed data into CyberCat — the correlation and response layer on top is what makes this different.",
            },
            {
              title: "How a case works",
              body: "Activity comes in, rules flag it, related flags get grouped into a case. You review what happened and who was involved, run the response actions you want, and close the case.",
            },
          ].map((card) => (
            <div
              key={card.title}
              className="rounded-lg border border-dossier-paperEdge bg-dossier-paper p-4"
            >
              <p className="mb-2 font-case text-xs font-semibold uppercase tracking-wider text-dossier-ink">
                {card.title}
              </p>
              <p className="text-xs leading-relaxed text-dossier-ink/50">{card.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── First-time CTA ───────────────────────────────────────────────── */}
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-dossier-paperEdge bg-dossier-paper px-5 py-4">
        <div>
          <p className="font-case text-xs font-semibold uppercase tracking-wider text-dossier-ink">
            First time here?
          </p>
          <p className="mt-1 text-xs text-dossier-ink/45">
            The tour walks you through a real case step by step. Or jump to the{" "}
            <Link href="/help#glossary" className="text-dossier-evidenceTape/70 underline-offset-2 hover:text-dossier-evidenceTape hover:underline transition-colors">
              glossary
            </Link>{" "}
            if you want plain-English definitions first.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            if (typeof window !== "undefined") {
              localStorage.removeItem("cybercat:tour:completed")
              window.location.assign("/incidents")
            }
          }}
          className="shrink-0 rounded border border-dossier-evidenceTape/25 px-4 py-2 font-case text-[10px] font-semibold uppercase tracking-widest text-dossier-evidenceTape/70 transition-colors hover:border-dossier-evidenceTape/60 hover:text-dossier-evidenceTape"
        >
          Take the tour →
        </button>
      </section>

    </div>
  )
}
