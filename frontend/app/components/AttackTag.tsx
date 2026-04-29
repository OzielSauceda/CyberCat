import Link from "next/link"
import type { AttackSource } from "../lib/api"

function mitreUrl(technique: string, subtechnique?: string | null): string {
  if (subtechnique) {
    const sub = subtechnique.split(".")[1]
    return `https://attack.mitre.org/techniques/${technique}/${sub}/`
  }
  return `https://attack.mitre.org/techniques/${technique}/`
}

interface AttackTagProps {
  technique: string
  subtechnique?: string | null
  source: AttackSource
  name?: string
}

export function AttackTag({ technique, subtechnique, source, name }: AttackTagProps) {
  const id = subtechnique ?? technique
  const url = mitreUrl(technique, subtechnique)
  const isRule = source === "rule_derived"
  const titleAttr = name ? `${id} — ${name}` : id

  return (
    <span className="inline-flex items-center gap-1 font-mono text-xs">
      <Link
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        title={titleAttr}
        className="text-indigo-300 hover:text-indigo-100 hover:underline"
      >
        {name ? `${id} · ${name}` : id}
      </Link>
      <span
        title={isRule ? "Rule derived" : "Correlator inferred"}
        className={`rounded px-1 text-xs ${
          isRule ? "bg-dossier-paperEdge text-dossier-ink/70" : "bg-violet-950 text-violet-400"
        }`}
      >
        {isRule ? "R" : "C"}
      </span>
    </span>
  )
}
