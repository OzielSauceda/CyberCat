import Link from "next/link"
import type { EntityKind } from "../lib/api"

const kindStyles: Record<EntityKind, string> = {
  user:       "text-indigo-200 bg-indigo-950/80 border-indigo-700",
  host:       "text-violet-200 bg-violet-950/80 border-violet-700",
  ip:         "text-cyan-200 bg-cyan-950/80 border-cyan-700",
  process:    "text-lime-200 bg-lime-950/80 border-lime-700",
  file:       "text-yellow-200 bg-yellow-950/80 border-yellow-700",
  observable: "text-pink-200 bg-pink-950/80 border-pink-700",
}

const kindPrefix: Record<EntityKind, string> = {
  user: "usr",
  host: "hst",
  ip: "ip",
  process: "proc",
  file: "file",
  observable: "obs",
}

interface EntityChipProps {
  kind: EntityKind
  naturalKey: string
  id?: string
  role?: string
}

export function EntityChip({ kind, naturalKey, id, role }: EntityChipProps) {
  const display =
    naturalKey.length > 28 ? naturalKey.slice(0, 26) + "…" : naturalKey

  const inner = (
    <>
      <span className="opacity-60">{kindPrefix[kind]}</span>
      <span>{display}</span>
    </>
  )

  const baseClass = `inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-xs ${kindStyles[kind]}`
  const title = role ? `${naturalKey} (${role})` : naturalKey

  if (id) {
    return (
      <Link
        href={`/entities/${id}`}
        className={`${baseClass} hover:underline cursor-pointer`}
        title={title}
      >
        {inner}
      </Link>
    )
  }

  return (
    <span className={baseClass} title={title}>
      {inner}
    </span>
  )
}
