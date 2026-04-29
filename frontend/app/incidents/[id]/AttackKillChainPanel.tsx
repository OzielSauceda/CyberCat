"use client"

import { useMemo, useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { AttackTag } from "../../components/AttackTag"
import { EmptyState } from "../../components/EmptyState"
import { Panel } from "../../components/Panel"
import { useAttackEntry } from "../../lib/attackCatalog"
import type { AttackRef } from "../../lib/api"
import { ATTACK_TACTIC_GLOSS } from "../../lib/labels"

// Full ATT&CK kill chain — used both as the canonical ordering for matched
// stations and as the optional "show all phases" detail strip.
const KILL_CHAIN = [
  { id: "reconnaissance",       short: "Recon",        full: "Reconnaissance",       mono: "RC" },
  { id: "resource-development", short: "Resources",    full: "Resource Development", mono: "RD" },
  { id: "initial-access",       short: "Initial",      full: "Initial Access",       mono: "IA" },
  { id: "execution",            short: "Execution",    full: "Execution",            mono: "EX" },
  { id: "persistence",          short: "Persistence",  full: "Persistence",          mono: "PE" },
  { id: "privilege-escalation", short: "PrivEsc",      full: "Privilege Escalation", mono: "PR" },
  { id: "defense-evasion",      short: "Evasion",      full: "Defense Evasion",      mono: "DE" },
  { id: "credential-access",    short: "Credentials",  full: "Credential Access",    mono: "CA" },
  { id: "discovery",            short: "Discovery",    full: "Discovery",            mono: "DI" },
  { id: "lateral-movement",     short: "Lateral",      full: "Lateral Movement",     mono: "LM" },
  { id: "collection",           short: "Collection",   full: "Collection",           mono: "CL" },
  { id: "command-and-control",  short: "C2",           full: "Command & Control",    mono: "C2" },
  { id: "exfiltration",         short: "Exfil",        full: "Exfiltration",         mono: "EF" },
  { id: "impact",               short: "Impact",       full: "Impact",               mono: "IM" },
] as const

type Tactic = (typeof KILL_CHAIN)[number]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AttackTagRow({ attack }: { attack: AttackRef }) {
  const tagId = attack.subtechnique ?? attack.technique
  const entry = useAttackEntry(tagId)
  return (
    <AttackTag
      technique={attack.technique}
      subtechnique={attack.subtechnique ?? null}
      source={attack.source}
      name={entry?.name}
    />
  )
}

interface StationProps {
  step: number
  tactic: Tactic
  refs: AttackRef[]
  isLast: boolean
  reducedMotion: boolean
}

function Station({ step, tactic, refs, isLast, reducedMotion }: StationProps) {
  const gloss = ATTACK_TACTIC_GLOSS[tactic.id]
  const baseDelay = reducedMotion ? 0 : 0.35 + step * 0.12
  // Tilt each stamp differently so the row looks hand-applied, not laser-cut.
  const tilt = ((step % 3) - 1) * 1.6

  return (
    <motion.div
      className="relative flex flex-col items-center"
      style={{ minWidth: 168 }}
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: baseDelay, duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
    >
      {/* Step number — small inked badge above the stamp */}
      <motion.div
        className="mb-1.5 font-case text-[10px] tracking-[0.25em] text-dossier-evidenceTape/55"
        initial={reducedMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: baseDelay + 0.05, duration: 0.3 }}
      >
        {String(step + 1).padStart(2, "0")}
      </motion.div>

      {/* Stamp circle */}
      <motion.div
        className="relative flex h-16 w-16 items-center justify-center"
        initial={reducedMotion ? false : { scale: 1.4, opacity: 0, rotate: tilt - 8 }}
        animate={{ scale: 1, opacity: 1, rotate: tilt }}
        transition={{
          delay: baseDelay,
          duration: 0.45,
          ease: [0.2, 1.4, 0.4, 1],
        }}
      >
        {/* Live pulse ring on the latest station only */}
        {isLast && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{
              border: "2px solid #00d4ff",
              boxShadow: "0 0 24px rgba(0,212,255,0.5)",
            }}
            animate={
              reducedMotion
                ? undefined
                : { scale: [1, 1.18, 1], opacity: [0.7, 0.15, 0.7] }
            }
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
        {/* Outer stamp ring */}
        <span
          className={`absolute inset-0 rounded-full border-[2.5px] ${
            isLast ? "border-dossier-evidenceTape/85" : "border-dossier-ink/35"
          }`}
          style={{
            boxShadow: isLast
              ? "0 0 20px rgba(0,212,255,0.35), inset 0 0 8px rgba(255,255,255,0.04)"
              : "inset 0 0 6px rgba(0,0,0,0.18)",
          }}
        />
        {/* Inner ring (decorative double border like a real stamp) */}
        <span
          className={`absolute inset-1.5 rounded-full border ${
            isLast ? "border-dossier-evidenceTape/35" : "border-dossier-ink/15"
          }`}
        />
        {/* Mono letters */}
        <span
          className={`relative font-case text-lg font-bold tracking-wide ${
            isLast ? "text-dossier-evidenceTape" : "text-dossier-ink/75"
          }`}
          style={
            isLast
              ? { textShadow: "0 0 14px rgba(0,212,255,0.55)" }
              : undefined
          }
        >
          {tactic.mono}
        </span>
      </motion.div>

      {/* "YOU ARE HERE" tag — only on the latest station */}
      {isLast && (
        <motion.div
          className="absolute -right-2 top-1 origin-bottom-left"
          initial={reducedMotion ? false : { opacity: 0, rotate: -18, x: 6 }}
          animate={{ opacity: 1, rotate: -10, x: 0 }}
          transition={{ delay: baseDelay + 0.4, duration: 0.4 }}
        >
          <span
            className="block whitespace-nowrap border border-dossier-redaction/55 bg-dossier-redaction/10 px-1.5 py-0.5 font-case text-[8px] font-bold uppercase tracking-[0.3em] text-dossier-redaction"
            style={{ boxShadow: "0 0 8px rgba(255,45,85,0.25)" }}
          >
            here
          </span>
        </motion.div>
      )}

      {/* Tactic name */}
      <motion.p
        className={`mt-2.5 font-case text-[11px] font-bold uppercase tracking-widest ${
          isLast ? "text-dossier-evidenceTape" : "text-dossier-ink/80"
        }`}
        initial={reducedMotion ? false : { opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: baseDelay + 0.15, duration: 0.3 }}
      >
        {tactic.full}
      </motion.p>

      {/* Plain-language gloss */}
      {gloss && (
        <motion.p
          className="mt-1 max-w-[180px] text-center text-[11px] leading-snug text-dossier-ink/55"
          initial={reducedMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: baseDelay + 0.22, duration: 0.35 }}
        >
          {gloss}
        </motion.p>
      )}

      {/* Technique chips */}
      {refs.length > 0 && (
        <motion.div
          className="mt-2 flex flex-wrap justify-center gap-1.5"
          initial={reducedMotion ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: baseDelay + 0.3, duration: 0.35 }}
        >
          {refs.map((ref, i) => (
            <AttackTagRow key={i} attack={ref} />
          ))}
        </motion.div>
      )}
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// All-phases compact strip (collapsible)
// ---------------------------------------------------------------------------

function AllPhasesStrip({ byTactic }: { byTactic: Map<string, AttackRef[]> }) {
  return (
    <div className="rounded-lg border border-dossier-paperEdge bg-dossier-stamp/60 p-3">
      <p className="mb-2 font-case text-[10px] uppercase tracking-widest text-dossier-ink/35">
        All ATT&amp;CK phases — for analyst reference
      </p>
      <div className="flex items-stretch gap-0 overflow-x-auto rounded border border-dossier-paperEdge">
        {KILL_CHAIN.map((tactic, i) => {
          const refs = byTactic.get(tactic.id) ?? []
          const matched = refs.length > 0
          const hasRule = refs.some((r) => r.source === "rule_derived")
          const hasInferred = refs.some((r) => r.source === "correlator_inferred")

          return (
            <div key={tactic.id} className="flex items-stretch">
              <div
                className={`flex flex-col items-center justify-between px-2 py-2 text-center ${
                  matched
                    ? "bg-dossier-evidenceTape/12 text-dossier-evidenceTape"
                    : "bg-transparent text-dossier-ink/30"
                }`}
                style={{ minWidth: 60 }}
                title={tactic.full}
              >
                <span className="font-mono text-[10px] leading-tight font-medium">
                  {tactic.short}
                </span>
                {matched ? (
                  <div className="mt-1 flex flex-col items-center gap-0.5">
                    <span className="rounded-full bg-dossier-evidenceTape/30 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-dossier-evidenceTape">
                      {refs.length}
                    </span>
                    <div className="flex gap-0.5">
                      {hasRule && (
                        <span
                          className="rounded bg-dossier-paperEdge px-1 text-[8px] leading-tight text-dossier-ink/70"
                          title="From a detection rule"
                        >
                          R
                        </span>
                      )}
                      {hasInferred && (
                        <span
                          className="rounded bg-violet-900/70 px-1 text-[8px] leading-tight text-violet-300"
                          title="Inferred by the correlator"
                        >
                          C
                        </span>
                      )}
                    </div>
                  </div>
                ) : (
                  <span className="mt-1 h-3.5" />
                )}
              </div>
              {i < KILL_CHAIN.length - 1 && (
                <div
                  className={`flex items-center self-stretch ${
                    matched && byTactic.has(KILL_CHAIN[i + 1].id)
                      ? "text-dossier-evidenceTape/65"
                      : "text-dossier-ink/15"
                  }`}
                >
                  <span className="px-0.5 text-[10px] leading-none">›</span>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-dossier-ink/40">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-4 rounded-sm bg-dossier-evidenceTape/15 border border-dossier-evidenceTape/30" />
          Step the attacker took
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded bg-dossier-paperEdge px-1 text-[8px] text-dossier-ink/70">R</span>
          From a detection rule
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded bg-violet-900/70 px-1 text-[8px] text-violet-300">C</span>
          Inferred by the correlator
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function AttackKillChainPanel({ attack }: { attack: AttackRef[] }) {
  const reducedMotion = useReducedMotion() ?? false
  const [showAllPhases, setShowAllPhases] = useState(false)

  const byTactic = useMemo(() => {
    const map = new Map<string, AttackRef[]>()
    for (const a of attack) {
      if (!map.has(a.tactic)) map.set(a.tactic, [])
      map.get(a.tactic)!.push(a)
    }
    return map
  }, [attack])

  // Matched tactics in canonical order — these become the route stations.
  const stations = useMemo(
    () => KILL_CHAIN.filter((t) => byTactic.has(t.id)),
    [byTactic],
  )

  if (attack.length === 0) {
    return (
      <Panel title="The route" count={0}>
        <EmptyState title="No ATT&CK techniques linked to this case yet" />
      </Panel>
    )
  }

  return (
    <Panel
      title="The route"
      count={stations.length}
      headerAction={
        <button
          type="button"
          onClick={() => setShowAllPhases((v) => !v)}
          className="font-case text-[10px] uppercase tracking-widest text-dossier-ink/40 transition-colors hover:text-dossier-evidenceTape"
        >
          {showAllPhases ? "Hide all phases" : "Show all phases →"}
        </button>
      }
    >
      <div className="space-y-5">
        {/* Caption */}
        <p className="text-xs leading-snug text-dossier-ink/55">
          The path the attacker has taken so far, ordered by ATT&amp;CK kill-chain phase.
          Each stamp is a phase that left evidence in this case.
        </p>

        {/* Route */}
        <div className="relative overflow-x-auto">
          <div
            className="relative flex items-start gap-0 px-2 py-3"
            style={{ minWidth: stations.length * 200 }}
          >
            {/* Hand-drawn ruled path behind the stations */}
            <RoutePath
              segments={Math.max(stations.length - 1, 0)}
              reducedMotion={reducedMotion}
            />

            {stations.map((tactic, idx) => (
              <div
                key={tactic.id}
                className="relative flex flex-1 items-start justify-center"
              >
                <Station
                  step={idx}
                  tactic={tactic}
                  refs={byTactic.get(tactic.id) ?? []}
                  isLast={idx === stations.length - 1}
                  reducedMotion={reducedMotion}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Optional analyst-detail strip */}
        {showAllPhases && <AllPhasesStrip byTactic={byTactic} />}
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Path drawn behind the route — inked solid for done segments, dashed for the
// last leg approaching the "now" station.
// ---------------------------------------------------------------------------

function RoutePath({
  segments,
  reducedMotion,
}: {
  segments: number
  reducedMotion: boolean
}) {
  if (segments < 1) return null
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        {/* Subtle imperfection so the line looks pen-drawn, not pixel-clean */}
        <filter id="kc-roughen" x="-2%" y="-50%" width="104%" height="200%">
          <feTurbulence baseFrequency="0.9" numOctaves="2" seed="3" />
          <feDisplacementMap in="SourceGraphic" scale="0.7" />
        </filter>
      </defs>
      <motion.line
        x1="6%"
        x2="94%"
        y1="56"
        y2="56"
        stroke="#0098c4"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeOpacity={0.55}
        filter="url(#kc-roughen)"
        initial={reducedMotion ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.9, ease: "easeInOut", delay: 0.1 }}
      />
    </svg>
  )
}
