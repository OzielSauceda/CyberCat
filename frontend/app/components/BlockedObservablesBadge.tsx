"use client"

import { useCallback } from "react"
import { listBlockedObservables } from "../lib/api"
import { usePolling } from "../lib/usePolling"

interface Props {
  naturalKey: string
}

export function BlockedObservablesBadge({ naturalKey }: Props) {
  const fetcher = useCallback(
    () => listBlockedObservables({ active: true, value: naturalKey }),
    [naturalKey],
  )
  const { data } = usePolling(fetcher, 30_000)

  const isBlocked = (data?.items?.length ?? 0) > 0
  if (!isBlocked) return null

  return (
    <span className="inline-flex items-center gap-1 rounded border border-red-800 bg-red-950 px-2 py-0.5 text-xs font-medium text-red-300">
      BLOCKED
    </span>
  )
}
