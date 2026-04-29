import type { Metadata } from "next"
import Link from "next/link"
import { GLOSSARY } from "../lib/glossary"

export const metadata: Metadata = { title: "Help & Glossary" }

const SORTED_SLUGS = Object.keys(GLOSSARY).sort() as (keyof typeof GLOSSARY)[]

// ---------------------------------------------------------------------------
// Investigation flow steps — static walkthrough
// ---------------------------------------------------------------------------

const FLOW_STEPS = [
  {
    n: "01",
    title: "Events arrive",
    body: "The built-in agent watches SSH logs, process activity, and network connections inside the lab container. Each raw log line gets standardized into a common format — who, what, when, where — and sent to the backend. Wazuh can send data too, as an alternative or alongside the agent.",
  },
  {
    n: "02",
    title: "Detection rules fire",
    body: "Every event is checked against the detection rule set. When a rule matches, it creates a Detection — noting the severity, how confident the match is, and which part of a known attack technique it maps to.",
  },
  {
    n: "03",
    title: "Related detections get grouped",
    body: "When a detection fires, CyberCat checks if it's connected to something already open — same user, same machine, part of the same attack chain. If it fits, it's added to that case. If not, a new case is created.",
  },
  {
    n: "04",
    title: "You investigate",
    body: "Open the case and review: which attack phases were involved, what happened and in what order, which users and machines are affected, and what the system recommends you do about it.",
  },
  {
    n: "05",
    title: "You take action",
    body: "Block an IP, isolate a machine in the lab, kill a process, or pull a file for review. Every action is risk-rated, timestamped, and logged. Most can be undone if you need to reverse course.",
  },
  {
    n: "06",
    title: "Case is closed",
    body: "Once the threat is handled and the root cause understood, mark the case resolved, then closed. Everything — the events, detections, actions, and notes — stays on record for review.",
  },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HelpPage() {
  return (
    <div className="space-y-14 py-2">

      {/* Page header */}
      <header className="border-b border-dossier-evidenceTape/15 pb-5">
        <p className="font-case text-[9px] uppercase tracking-[0.35em] text-dossier-evidenceTape/50 mb-1.5">
          Reference
        </p>
        <h1 className="font-case text-2xl text-dossier-ink">Help &amp; Glossary</h1>
        <p className="mt-1 text-xs text-dossier-ink/50">
          Plain-English explanations for every term in the app. New to security? Start here. Anywhere you see an underlined word in the app, hovering it pops up the same definition you&apos;ll find below.
        </p>
      </header>

      {/* What is CyberCat */}
      <section>
        <h2 className="font-case text-sm uppercase tracking-[0.2em] text-dossier-ink mb-4">
          What is CyberCat?
        </h2>
        <div className="max-w-2xl space-y-3 text-sm leading-relaxed text-dossier-ink/60">
          <p>
            CyberCat watches your systems for suspicious login and endpoint activity, groups related events into cases, and helps you understand and respond to what&apos;s happening — with a clear audit trail at every step.
          </p>
          <p>
            It&apos;s not a log aggregator, not an antivirus, and not a Wazuh add-on. Tools like Wazuh feed raw data in — CyberCat&apos;s job is to make sense of that data and surface what actually needs your attention.
          </p>
          <p>
            It runs entirely on a single machine. The whole stack — database, backend, frontend, agent, and lab container — uses under 6 GB of RAM when idle.
          </p>
        </div>
      </section>

      {/* How an investigation works */}
      <section>
        <h2 className="font-case text-sm uppercase tracking-[0.2em] text-dossier-ink mb-4">
          How an Investigation Works
        </h2>
        <ol className="max-w-2xl space-y-4">
          {FLOW_STEPS.map((step) => (
            <li key={step.n} className="flex gap-4">
              <span className="mt-0.5 shrink-0 font-case text-xs text-dossier-evidenceTape/50 w-6">
                {step.n}
              </span>
              <div>
                <p className="font-case text-xs text-dossier-ink mb-1">{step.title}</p>
                <p className="text-xs leading-relaxed text-dossier-ink/60">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Glossary */}
      <section id="glossary">
        <h2 className="font-case text-sm uppercase tracking-[0.2em] text-dossier-ink mb-1">
          Glossary
        </h2>
        <p className="mb-6 text-xs text-dossier-ink/30">
          {SORTED_SLUGS.length} terms · alphabetical order
        </p>

        <dl className="max-w-2xl divide-y divide-dossier-paperEdge">
          {SORTED_SLUGS.map((slug) => {
            const entry = GLOSSARY[slug]
            return (
              <div
                key={slug}
                id={slug}
                className="scroll-mt-20 py-4 first:pt-0"
              >
                <dt className="mb-1 flex items-baseline gap-3">
                  <span className="font-case text-sm text-dossier-ink">
                    {entry.title}
                  </span>
                  <span className="font-mono text-[10px] text-dossier-evidenceTape/30">
                    #{slug}
                  </span>
                </dt>
                <dd className="text-xs leading-relaxed text-dossier-ink/60">
                  {entry.long}
                </dd>
              </div>
            )
          })}
        </dl>
      </section>

      {/* Footer nav */}
      <section className="border-t border-dossier-paperEdge pt-6">
        <div className="flex flex-wrap gap-6 text-xs text-dossier-ink/35">
          <Link href="/" className="transition-colors hover:text-dossier-ink">← Home</Link>
          <Link href="/incidents" className="transition-colors hover:text-dossier-ink">Incidents</Link>
          <Link href="/detections" className="transition-colors hover:text-dossier-ink">Detections</Link>
          <Link href="/actions" className="transition-colors hover:text-dossier-ink">Actions</Link>
          <span className="ml-auto">Runbook: <code className="font-mono text-dossier-evidenceTape/35">docs/runbook.md</code></span>
        </div>
      </section>

    </div>
  )
}
