"use client"

import { useEffect, useRef, useState } from "react"
import { ApiError, createTransition, type IncidentStatus } from "../lib/api"
import { allowedNextStatuses, reasonRequired } from "../lib/transitions"
import { useCanMutate } from "../lib/SessionContext"
import { ConfirmDialog } from "./ConfirmDialog"
import { StatusPill } from "./StatusPill"
import { useToast } from "./Toast"

interface TransitionMenuProps {
  incidentId: string
  currentStatus: IncidentStatus
  onTransitioned: () => void
}

export function TransitionMenu({ incidentId, currentStatus, onTransitioned }: TransitionMenuProps) {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<IncidentStatus | null>(null)
  const [reason, setReason] = useState("")
  const [pending, setPending] = useState(false)
  const [inlineError, setInlineError] = useState<{ code: string; message: string } | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const options = allowedNextStatuses(currentStatus)

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  const handleSelect = (status: IncidentStatus) => {
    setSelected(status)
    setReason("")
    setInlineError(null)
    setOpen(false)
  }

  const handleConfirm = async () => {
    if (!selected) return
    if (reasonRequired(selected) && !reason.trim()) {
      setInlineError({ code: "reason_required", message: "A reason is required for this transition." })
      return
    }
    setPending(true)
    setInlineError(null)
    try {
      await createTransition(incidentId, { to_status: selected, reason: reason.trim() || undefined })
      push({ variant: "success", title: `Status updated to ${selected}` })
      onTransitioned()
      setSelected(null)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "reason_required" || err.code === "invalid_transition") {
          setInlineError({ code: err.code, message: err.message })
        } else {
          setSelected(null)
          push({ variant: "error", title: "Transition failed", body: err.message })
        }
      } else {
        setSelected(null)
        push({ variant: "error", title: "Transition failed" })
      }
    } finally {
      setPending(false)
    }
  }

  if (options.length === 0) return null

  return (
    <div className="relative" ref={menuRef}>
      <button
        ref={buttonRef}
        onClick={() => setOpen((v) => !v)}
        disabled={!canMutate}
        title={!canMutate ? "Read-only role" : undefined}
        className="rounded border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Transition…
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 z-40 flex flex-col gap-0.5 rounded-lg border border-zinc-700 bg-zinc-900 p-1 shadow-xl min-w-[140px]">
          {options.map((status) => (
            <button
              key={status}
              onClick={() => handleSelect(status)}
              className="flex items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-zinc-800 transition-colors"
            >
              <StatusPill status={status} />
            </button>
          ))}
        </div>
      )}

      {selected && (
        <ConfirmDialog
          open={selected !== null}
          title="Transition incident"
          body={
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <StatusPill status={currentStatus} />
                <span className="text-zinc-500">→</span>
                <StatusPill status={selected} />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-zinc-400">
                  Reason
                  {reasonRequired(selected) && (
                    <span className="ml-1 text-red-400">*</span>
                  )}
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => { setReason(e.target.value); setInlineError(null) }}
                  rows={2}
                  placeholder={reasonRequired(selected) ? "Required" : "Optional"}
                  disabled={pending}
                  className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 disabled:opacity-50 resize-none"
                />
                {inlineError?.code === "reason_required" && (
                  <p className="text-xs text-red-400">{inlineError.message}</p>
                )}
              </div>
              {inlineError && inlineError.code !== "reason_required" && (
                <p className="text-xs text-red-400">{inlineError.message}</p>
              )}
            </div>
          }
          confirmLabel="Transition"
          pending={pending}
          onConfirm={handleConfirm}
          onClose={() => { if (!pending) { setSelected(null); setInlineError(null) } }}
        />
      )}
    </div>
  )
}
