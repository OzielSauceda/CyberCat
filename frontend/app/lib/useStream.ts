"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { connectStream, StreamEvent, StreamStatus, StreamTopic } from "./streaming"
import { usePolling } from "./usePolling"

// Used by useStream as fallback; do not delete usePolling.

export interface StreamResult<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
  refetch: () => void
  streamStatus: StreamStatus | "idle"
}

export interface UseStreamOptions<T> {
  topics: StreamTopic[]
  fetcher: () => Promise<T>
  /** Return true if this event should trigger a refetch. */
  shouldRefetch: (event: StreamEvent) => boolean
  /** Safety-net poll interval while SSE is connected (default: 60s). */
  fallbackPollMs?: number
}

/**
 * Like usePolling but driven by SSE. Falls back to faster polling when SSE fails.
 * Keeps usePolling as a slow safety-net even when SSE is live.
 */
export function useStream<T>({
  topics,
  fetcher,
  shouldRefetch,
  fallbackPollMs = 60_000,
}: UseStreamOptions<T>): StreamResult<T> {
  const [streamStatus, setStreamStatus] = useState<StreamStatus | "idle">("idle")

  // The effective poll interval: slow when SSE is connected/connecting, fast when failed
  const pollMs = streamStatus === "failed" ? Math.min(fallbackPollMs, 10_000) : fallbackPollMs

  const { data, error, loading, refetch } = usePolling(fetcher, pollMs)

  // Stable refs so the SSE callbacks always see the latest values
  const shouldRefetchRef = useRef(shouldRefetch)
  shouldRefetchRef.current = shouldRefetch
  const refetchRef = useRef(refetch)
  refetchRef.current = refetch

  // Debounce timer: coalesce rapid event bursts into one refetch
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scheduleRefetch = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      refetchRef.current()
      debounceRef.current = null
    }, 300)
  }, [])

  const topicsKey = topics.join(",")

  useEffect(() => {
    const conn = connectStream({
      topics,
      onEvent(event) {
        if (shouldRefetchRef.current(event)) {
          scheduleRefetch()
        }
      },
      onStatusChange(status) {
        setStreamStatus(status)
        if (status === "open") {
          // Refetch once on (re)connect to catch anything missed during gap
          scheduleRefetch()
        }
      },
    })

    const onVisible = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        refetchRef.current()
      }
    }
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisible)
    }

    return () => {
      conn.close()
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisible)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicsKey, scheduleRefetch])

  return { data, error, loading, refetch, streamStatus }
}
