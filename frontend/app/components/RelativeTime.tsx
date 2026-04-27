"use client"

import { formatDistanceToNow } from "date-fns"
import { useEffect, useState } from "react"

function fmt(iso: string): string {
  return formatDistanceToNow(new Date(iso), { addSuffix: true })
}

export function RelativeTime({ at }: { at: string }) {
  const [text, setText] = useState(() => fmt(at))

  useEffect(() => {
    setText(fmt(at))
    const id = setInterval(() => setText(fmt(at)), 60_000)
    return () => clearInterval(id)
  }, [at])

  return (
    <time
      dateTime={at}
      title={new Date(at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "medium",
      })}
      className="text-zinc-400"
    >
      {text}
    </time>
  )
}
