"use client"

import { useMemo } from "react"
import { AttackTag } from "../../components/AttackTag"
import { EmptyState } from "../../components/EmptyState"
import { Panel } from "../../components/Panel"
import { useAttackEntry } from "../../lib/attackCatalog"
import type { AttackRef } from "../../lib/api"

const KILL_CHAIN = [
  { id: "reconnaissance",       short: "Recon",        full: "Reconnaissance" },
  { id: "resource-development", short: "Resources",    full: "Resource Development" },
  { id: "initial-access",       short: "Initial",      full: "Initial Access" },
  { id: "execution",            short: "Execution",    full: "Execution" },
  { id: "persistence",          short: "Persistence",  full: "Persistence" },
  { id: "privilege-escalation", short: "PrivEsc",      full: "Privilege Escalation" },
  { id: "defense-evasion",      short: "Evasion",      full: "Defense Evasion" },
  { id: "credential-access",    short: "Cred Access",  full: "Credential Access" },
  { id: "discovery",            short: "Discovery",    full: "Discovery" },
  { id: "lateral-movement",     short: "Lateral",      full: "Lateral Movement" },
  { id: "collection",           short: "Collection",   full: "Collection" },
  { id: "command-and-control",  short: "C2",           full: "Command & Control" },
  { id: "exfiltration",         short: "Exfil",        full: "Exfiltration" },
  { id: "impact",               short: "Impact",       full: "Impact" },
] as const

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

export function AttackKillChainPanel({ attack }: { attack: AttackRef[] }) {
  const byTactic = useMemo(() => {
    const map = new Map<string, AttackRef[]>()
    for (const a of attack) {
      if (!map.has(a.tactic)) map.set(a.tactic, [])
      map.get(a.tactic)!.push(a)
    }
    return map
  }, [attack])

  const matchedTactics = KILL_CHAIN.filter((t) => byTactic.has(t.id))

  return (
    <Panel title="ATT&CK kill chain" count={attack.length}>
      {attack.length === 0 ? (
        <EmptyState title="No ATT&CK techniques linked" />
      ) : (
        <div className="space-y-5">
          {/* Kill chain strip */}
          <div className="flex items-stretch gap-0 overflow-x-auto rounded-lg border border-zinc-800">
            {KILL_CHAIN.map((tactic, i) => {
              const matched = byTactic.has(tactic.id)
              const refs = byTactic.get(tactic.id) ?? []
              const hasRuleDerived = refs.some((r) => r.source === "rule_derived")
              const hasInferred = refs.some((r) => r.source === "correlator_inferred")

              return (
                <div key={tactic.id} className="flex items-stretch">
                  <div
                    className={`flex flex-col items-center justify-between px-2 py-2 text-center transition-colors ${
                      matched
                        ? "bg-indigo-950/60 text-indigo-300"
                        : "bg-zinc-900 text-zinc-700"
                    }`}
                    style={{ minWidth: 62 }}
                    title={tactic.full}
                  >
                    <span className="text-[10px] font-mono leading-tight font-medium">
                      {tactic.short}
                    </span>
                    {matched ? (
                      <div className="mt-1.5 flex flex-col items-center gap-0.5">
                        <span className="rounded-full bg-indigo-800 px-1.5 py-0.5 text-[9px] font-semibold text-indigo-200 leading-none">
                          {refs.length}
                        </span>
                        <div className="flex gap-0.5">
                          {hasRuleDerived && (
                            <span className="rounded bg-zinc-700 px-1 text-[8px] text-zinc-300 leading-tight">
                              R
                            </span>
                          )}
                          {hasInferred && (
                            <span className="rounded bg-violet-900 px-1 text-[8px] text-violet-300 leading-tight">
                              C
                            </span>
                          )}
                        </div>
                      </div>
                    ) : (
                      <span className="mt-1.5 h-4" />
                    )}
                  </div>
                  {i < KILL_CHAIN.length - 1 && (
                    <div
                      className={`flex items-center self-stretch ${
                        matched && byTactic.has(KILL_CHAIN[i + 1].id)
                          ? "text-indigo-700"
                          : "text-zinc-800"
                      }`}
                    >
                      <span className="text-[10px] px-0.5 leading-none">›</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Matched technique details */}
          {matchedTactics.length > 0 && (
            <div className="space-y-3">
              {matchedTactics.map((tactic) => (
                <div key={tactic.id}>
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-indigo-500">
                    {tactic.full}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {byTactic.get(tactic.id)!.map((ref, i) => (
                      <AttackTagRow key={i} attack={ref} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  )
}
