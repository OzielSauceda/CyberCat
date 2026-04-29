"use client"

import { useCallback, useEffect, useRef, useState } from "react"

export interface PollingResult<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
  refetch: () => void
}

/**
 * Polls `fetcher` immediately on mount and then every `intervalMs`.
 * Pauses when the tab is hidden; resumes and re-fetches when visible again.
 * On refetch errors, keeps the last-good data and surfaces the error separately.
 * Never returns to loading=true after the first fetch completes.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): PollingResult<T> {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<Error>()
  const [loading, setLoading] = useState(true)
  // tick is used to imperatively trigger a refetch
  const [tick, setTick] = useState(0)
  // stable ref so interval/visibilitychange callbacks always call latest fetcher
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  // When the fetcher identity changes (filter params changed), immediately
  // re-fetch instead of waiting for the next polling interval.
  const prevFetcherRef = useRef(fetcher)
  useEffect(() => {
    if (prevFetcherRef.current !== fetcher) {
      prevFetcherRef.current = fetcher
      setLoading(true)
      setTick((t) => t + 1)
    }
  }, [fetcher])

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return
      try {
        const result = await fetcherRef.current()
        if (!cancelled) {
          setData(result)
          setError(undefined)
          setLoading(false)
        }
      } catch (e) {
        if (!cancelled) {
          if (e instanceof Error) setError(e)
          setLoading(false)
        }
      }
    }

    run()
    const id = setInterval(run, intervalMs)

    const onVisible = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") run()
    }
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisible)
    }

    return () => {
      cancelled = true
      clearInterval(id)
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisible)
      }
    }
  }, [intervalMs, tick])

  const refetch = useCallback(() => setTick((t) => t + 1), [])

  return { data, error, loading, refetch }
}
