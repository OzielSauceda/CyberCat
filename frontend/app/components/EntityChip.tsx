import Link from "next/link"
import type { EntityKind } from "../lib/api"

const kindStyles: Record<EntityKind, string> = {
  user: "text-indigo-300 bg-indigo-950 border-indigo-800",
  host: "text-violet-300 bg-violet-950 border-violet-800",
  ip: "text-cyan-300 bg-cyan-950 border-cyan-800",
  process: "text-lime-300 bg-lime-950 border-lime-800",
  file: "text-yellow-300 bg-yellow-950 border-yellow-800",
  observable: "text-pink-300 bg-pink-950 border-pink-800",
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
