"use client"

import { useState } from "react"

export function JsonBlock({ data }: { data: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  const count = Object.keys(data).length

  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        aria-expanded={open}
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        <span>
          {count} {count === 1 ? "field" : "fields"}
        </span>
      </button>
      {open && (
        <pre className="mt-1.5 overflow-x-auto rounded bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-300 font-mono">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}
