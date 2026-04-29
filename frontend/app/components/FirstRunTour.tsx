"use client"

import { AnimatePresence, motion } from "framer-motion"
import { usePathname, useRouter } from "next/navigation"
import { useCallback, useEffect, useRef, useState } from "react"
import { listIncidents } from "../lib/api"

export const TOUR_KEY = "cybercat:tour:completed"
export const TOUR_RESTART_EVENT = "cybercat:tour:restart"

interface Rect { top: number; left: number; width: number; height: number }

const STEPS = [
  {
    dataAttr: "incident-card-first",
    title: "This is an incident.",
    body: "A group of suspicious events that CyberCat linked into a single case. Severity, status, and who's involved — all at a glance. Click any card to dig into the full investigation.",
  },
  {
    dataAttr: "kill-chain-panel",
    title: "This is the kill chain.",
    body: "Each highlighted box is a phase of the attack, ordered from how they got in to what they did. More boxes lit up means more of the attack is documented and understood.",
  },
  {
    dataAttr: "actions-panel",
    title: "These are your response options.",
    body: "Block an IP, isolate a machine in the lab, or kill a process. Every action is rated by risk and logged — and most can be undone if you change your mind.",
  },
]

function getRect(attr: string): Rect | null {
  const el = document.querySelector(`[data-tour="${attr}"]`)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { top: r.top - 8, left: r.left - 8, width: r.width + 16, height: r.height + 16 }
}

function elevateTourTarget(attr: string): (() => void) {
  const el = document.querySelector<HTMLElement>(`[data-tour="${attr}"]`)
  if (!el) return () => {}
  const prev = { position: el.style.position, zIndex: el.style.zIndex }
  el.style.position = "relative"
  el.style.zIndex = "45"
  return () => {
    el.style.position = prev.position
    el.style.zIndex = prev.zIndex
  }
}

export function FirstRunTour() {
  const router = useRouter()
  const pathname = usePathname()
  const [active, setActive] = useState(false)
  const [step, setStep] = useState(0)
  const [firstId, setFirstId] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<Rect | null>(null)
  const rafRef = useRef<number | null>(null)
  const restoreRef = useRef<(() => void) | null>(null)

  const startTour = useCallback((id: string | null) => {
    setFirstId(id)
    setStep(0)
    setActive(true)
  }, [])

  // Auto-start: check flag + incidents on mount
  useEffect(() => {
    if (localStorage.getItem(TOUR_KEY)) return
    listIncidents({ status: "new,triaged,investigating,contained", limit: 1 })
      .then((res) => {
        const id = res.items[0]?.id ?? null
        if (res.items.length > 0) {
          if (!pathname.startsWith("/incidents")) router.push("/incidents")
          startTour(id)
        }
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Listen for manual restart event (from HelpMenu)
  useEffect(() => {
    const handler = () => {
      listIncidents({ status: "new,triaged,investigating,contained", limit: 1 })
        .then((res) => {
          const id = res.items[0]?.id ?? null
          if (!pathname.startsWith("/incidents")) router.push("/incidents")
          startTour(id)
        })
        .catch(() => startTour(null))
    }
    window.addEventListener(TOUR_RESTART_EVENT, handler)
    return () => window.removeEventListener(TOUR_RESTART_EVENT, handler)
  }, [pathname, router, startTour])

  const updateHighlight = useCallback(() => {
    if (!active) return
    // Restore previous elevated element
    if (restoreRef.current) {
      restoreRef.current()
      restoreRef.current = null
    }
    const attr = STEPS[step]?.dataAttr
    if (!attr) { setHighlight(null); return }
    const rect = getRect(attr)
    setHighlight(rect)
    if (rect) restoreRef.current = elevateTourTarget(attr)
  }, [active, step])

  // Re-measure when step or pathname changes (after short delay for DOM settle)
  useEffect(() => {
    if (!active) return
    const id = setTimeout(updateHighlight, 150)
    return () => clearTimeout(id)
  }, [active, step, pathname, updateHighlight])

  // Re-measure on scroll / resize
  useEffect(() => {
    if (!active) return
    const onFrame = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(updateHighlight)
    }
    window.addEventListener("scroll", onFrame, { passive: true })
    window.addEventListener("resize", onFrame, { passive: true })
    return () => {
      window.removeEventListener("scroll", onFrame)
      window.removeEventListener("resize", onFrame)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [active, updateHighlight])

  const dismiss = useCallback(() => {
    if (restoreRef.current) { restoreRef.current(); restoreRef.current = null }
    setActive(false)
    setHighlight(null)
    localStorage.setItem(TOUR_KEY, "1")
  }, [])

  const next = useCallback(() => {
    if (step === 0) {
      if (firstId) {
        router.push(`/incidents/${firstId}`)
      }
      setStep(1)
    } else if (step === 1) {
      setStep(2)
      setTimeout(() => {
        document.querySelector('[data-tour="actions-panel"]')?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        })
      }, 200)
    } else {
      dismiss()
    }
  }, [step, firstId, router, dismiss])

  if (!active) return null

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <AnimatePresence>
      <motion.div
        key="tour-root"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="pointer-events-none fixed inset-0 z-40"
      >
        {/* Semi-transparent backdrop — the ring's box-shadow cuts out the spotlight */}
        <div className="absolute inset-0 bg-black/50" />

        {/* Spotlight ring */}
        {highlight && (
          <motion.div
            key={`ring-${step}`}
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute rounded-lg"
            style={{
              top: highlight.top,
              left: highlight.left,
              width: highlight.width,
              height: highlight.height,
              // Punch a transparent hole through the backdrop above
              backgroundColor: "transparent",
              boxShadow:
                "0 0 0 9999px transparent, 0 0 0 2px rgba(196,164,98,0.55), 0 0 16px 2px rgba(196,164,98,0.18)",
              border: "1.5px solid rgba(196,164,98,0.45)",
            }}
          />
        )}
      </motion.div>

      {/* Tour HUD — pointer-events on, sits above the backdrop */}
      <motion.div
        key={`hud-${step}`}
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        transition={{ duration: 0.22 }}
        className="pointer-events-auto fixed bottom-6 left-1/2 z-50 w-[360px] -translate-x-1/2 rounded-lg border border-dossier-paperEdge bg-dossier-paper shadow-2xl"
      >
        {/* Header with step dots */}
        <div className="flex items-center border-b border-dossier-paperEdge px-4 py-2.5">
          <span className="font-case text-[9px] uppercase tracking-[0.3em] text-dossier-evidenceTape/60">
            Field Guide
          </span>
          <div className="ml-auto flex gap-1.5">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`h-1 w-5 rounded-full transition-colors duration-300 ${
                  i === step
                    ? "bg-dossier-evidenceTape/70"
                    : i < step
                    ? "bg-dossier-stamp"
                    : "bg-dossier-paperEdge"
                }`}
              />
            ))}
          </div>
        </div>

        {/* Step content */}
        <div className="px-4 py-4">
          <p className="font-case text-sm text-dossier-ink mb-2">{current.title}</p>
          <p className="text-xs leading-relaxed text-dossier-ink/60">{current.body}</p>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between border-t border-dossier-paperEdge px-4 py-3">
          <button
            onClick={dismiss}
            className="text-xs text-dossier-ink/30 transition-colors hover:text-dossier-ink/60"
          >
            Skip tour
          </button>
          <button
            onClick={next}
            className="rounded border border-dossier-evidenceTape/30 px-3 py-1.5 font-case text-[10px] uppercase tracking-[0.2em] text-dossier-evidenceTape/70 transition-colors hover:border-dossier-evidenceTape/55 hover:text-dossier-evidenceTape"
          >
            {isLast ? "Done" : "Next →"}
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
