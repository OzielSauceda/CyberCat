"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import clsx from "clsx"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ToastVariant = "success" | "error" | "info"

export interface ToastOptions {
  variant: ToastVariant
  title: string
  body?: string
}

interface ToastItem extends ToastOptions {
  id: string
}

interface ToastApi {
  push: (opts: ToastOptions) => void
  dismiss: (id: string) => void
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const ToastCtx = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx)
  if (!ctx) throw new Error("useToast must be inside ToastProvider")
  return ctx
}

// ---------------------------------------------------------------------------
// Single toast visual
// ---------------------------------------------------------------------------

const variantStyles: Record<ToastVariant, string> = {
  success: "border-emerald-800 bg-emerald-950 text-emerald-200",
  error:   "border-red-800 bg-red-950 text-red-200",
  info:    "border-sky-800 bg-sky-950 text-sky-200",
}

function ToastItem({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  return (
    <div
      role={item.variant === "error" ? "alert" : "status"}
      className={clsx(
        "flex items-start gap-3 rounded-lg border p-3 shadow-lg text-sm max-w-sm w-full",
        variantStyles[item.variant],
      )}
    >
      <div className="flex-1 min-w-0">
        <p className="font-medium leading-snug">{item.title}</p>
        {item.body && (
          <p className="mt-0.5 text-xs opacity-80 leading-snug">{item.body}</p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity text-xs leading-none"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Provider (manages state + renders viewport)
// ---------------------------------------------------------------------------

let _counter = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const push = useCallback(
    (opts: ToastOptions) => {
      const id = `toast-${++_counter}`
      setToasts((prev) => [...prev, { ...opts, id }])
      if (opts.variant !== "error") {
        const timer = setTimeout(() => dismiss(id), 4_000)
        timers.current.set(id, timer)
      }
    },
    [dismiss],
  )

  useEffect(() => {
    const currentTimers = timers.current
    return () => {
      currentTimers.forEach(clearTimeout)
      currentTimers.clear()
    }
  }, [])

  return (
    <ToastCtx.Provider value={{ push, dismiss }}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2 pointer-events-none"
      >
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem item={t} onDismiss={() => dismiss(t.id)} />
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
