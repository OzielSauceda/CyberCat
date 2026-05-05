"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import {
  ApiError,
  splitIncident,
  type IncidentDetail,
} from "../../lib/api"
import { useToast } from "../../components/Toast"
import { useCanMutate } from "../../lib/SessionContext"

interface SplitButtonProps {
  incident: IncidentDetail
  splitMode: boolean
  selectedEventIds: Set<string>
  onToggleSplitMode: () => void
  onClearSelection: () => void
}

/**
 * SplitButton — top-right action that toggles "split mode" on the incident
 * timeline. When split mode is on, the timeline renders a checkbox per
 * event row; when at least one event is selected, the button morphs into
 * a "Split N events into new incident…" confirm action that opens a
 * reason modal.
 *
 * Per ADR-0015, split children are non-canonical (no parent_incident_id);
 * the audit link is the IncidentTransition row.
 *
 * Aesthetic: dossier "evidence-tape" cyan when toggled on (signals "you're
 * pulling evidence off"). Confirm button uses cyber-orange to match the
 * destructive-but-reversible classification.
 */
export function SplitButton({
  incident,
  splitMode,
  selectedEventIds,
  onToggleSplitMode,
  onClearSelection,
}: SplitButtonProps) {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const router = useRouter()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<Element | null>(null)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [reason, setReason] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedCount = selectedEventIds.size
  const reasonValid = reason.trim().length >= 1 && reason.length <= 500
  const sourceClosed =
    incident.status === "closed" || incident.status === "merged"

  // Open / close the confirm dialog
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (confirmOpen) {
      returnFocusRef.current = document.activeElement
      dialog.showModal()
      setReason("")
      setError(null)
    } else {
      dialog.close()
      const el = returnFocusRef.current
      if (el instanceof HTMLElement) el.focus()
    }
  }, [confirmOpen])

  const handleSplit = async () => {
    if (!reasonValid || pending || selectedCount === 0) return
    setPending(true)
    setError(null)
    try {
      const child = await splitIncident(incident.id, {
        event_ids: Array.from(selectedEventIds),
        entity_ids: [],
        reason: reason.trim(),
      })
      push({
        variant: "success",
        title: "Incident split",
        body: `${selectedCount} event${selectedCount === 1 ? "" : "s"} moved to new incident`,
      })
      setConfirmOpen(false)
      onClearSelection()
      onToggleSplitMode() // Close split mode
      router.push(`/incidents/${child.id}`)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Split failed"
      setError(message)
    } finally {
      setPending(false)
    }
  }

  if (sourceClosed) {
    // Hide entirely on closed/merged sources — split is forbidden by the API.
    return null
  }

  // --- "Split mode OFF" — single toggle button
  if (!splitMode) {
    return (
      <button
        type="button"
        onClick={onToggleSplitMode}
        disabled={!canMutate}
        title={!canMutate ? "Read-only role" : "Pick events to split off"}
        className="rounded border border-dossier-paperEdge bg-dossier-stamp px-3 py-1.5 font-case text-[10px] font-semibold uppercase tracking-widest text-dossier-ink/55 transition-all hover:border-dossier-evidenceTape/40 hover:text-dossier-evidenceTape disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:border-dossier-paperEdge disabled:hover:text-dossier-ink/55"
      >
        Split…
      </button>
    )
  }

  // --- "Split mode ON" — toolbar with cancel + confirm
  return (
    <>
      <div className="flex items-center gap-2 rounded border border-dossier-evidenceTape/50 bg-dossier-evidenceTape/10 px-3 py-1 shadow-[0_0_18px_rgba(0,212,255,0.18)]">
        <span className="font-case text-[10px] uppercase tracking-widest text-dossier-evidenceTape">
          Split mode
        </span>
        <span className="font-mono text-[10px] text-dossier-ink/40">·</span>
        <span className="font-mono text-[10px] text-dossier-ink/70">
          {selectedCount} selected
        </span>
        <span className="font-mono text-[10px] text-dossier-ink/30">·</span>
        <button
          type="button"
          onClick={() => {
            onClearSelection()
            onToggleSplitMode()
          }}
          className="font-case text-[10px] uppercase tracking-widest text-dossier-ink/50 transition-colors hover:text-dossier-ink"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={selectedCount === 0}
          className="rounded border border-cyber-orange/60 bg-cyber-orange/15 px-2.5 py-0.5 font-case text-[10px] font-semibold uppercase tracking-widest text-cyber-orange transition-all hover:bg-cyber-orange/30 hover:shadow-[0_0_16px_rgba(255,107,53,0.35)] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-cyber-orange/15 disabled:hover:shadow-none"
        >
          Confirm split →
        </button>
      </div>

      {/* Confirm dialog */}
      <dialog
        ref={dialogRef}
        onCancel={(e) => {
          e.preventDefault()
          if (!pending) setConfirmOpen(false)
        }}
        className="m-auto w-full max-w-lg rounded-xl bg-transparent p-0 outline-none backdrop:bg-dossier-stamp/85 backdrop:backdrop-blur-sm"
      >
        <div
          className="flex flex-col gap-5 rounded-xl border border-dossier-paperEdge bg-dossier-paper p-6 shadow-dossier"
          style={{ boxShadow: "inset 0 0 60px rgba(0,212,255,0.025), 0 0 0 1px rgba(0,212,255,0.07), 0 12px 48px rgba(0,0,0,0.85)" }}
        >
          <div className="flex items-start justify-between gap-4 border-b border-dossier-paperEdge pb-4">
            <div>
              <p className="font-case text-[9px] font-semibold uppercase tracking-[0.25em] text-cyber-orange">
                Case file action — split
              </p>
              <h2 className="mt-1 text-base font-semibold text-dossier-ink">
                Lift {selectedCount} event{selectedCount === 1 ? "" : "s"} into a new incident
              </h2>
              <p className="mt-1 text-xs text-dossier-ink/50">
                Source:{" "}
                <span className="font-mono text-dossier-evidenceTape/80">
                  INC-{incident.id.slice(-8).toUpperCase()}
                </span>
              </p>
            </div>
            <span
              className="select-none border-2 border-cyber-orange/40 px-2 py-0.5 font-case text-[9px] uppercase tracking-widest text-cyber-orange/70"
              style={{ transform: "rotate(-3deg)" }}
            >
              destructive
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 rounded border border-dossier-evidenceTape/25 bg-dossier-stamp/60 p-3 text-center">
            <div>
              <p className="font-mono text-2xl font-semibold text-dossier-ink">
                {incident.timeline.length - selectedCount}
              </p>
              <p className="mt-1 font-case text-[9px] uppercase tracking-widest text-dossier-ink/40">
                events left on source
              </p>
            </div>
            <div className="border-l border-dossier-paperEdge pl-3">
              <p className="font-mono text-2xl font-semibold text-cyber-orange">
                {selectedCount}
              </p>
              <p className="mt-1 font-case text-[9px] uppercase tracking-widest text-cyber-orange/80">
                → events on new incident
              </p>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="font-case text-[10px] font-semibold uppercase tracking-widest text-dossier-ink/60">
              Reason for the split <span className="text-dossier-redaction/70">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={pending}
              placeholder="e.g. these events belong to a separate workstation issue, not the same intrusion"
              maxLength={500}
              rows={2}
              className="w-full resize-none rounded border border-dossier-paperEdge bg-dossier-stamp px-3 py-2 text-sm text-dossier-ink placeholder-dossier-ink/30 outline-none transition-colors focus:border-dossier-evidenceTape/60 disabled:opacity-50"
            />
            <p className="text-right font-mono text-[10px] text-dossier-ink/30">
              {reason.length} / 500
            </p>
          </div>

          {error && (
            <div className="rounded border border-dossier-redaction/40 bg-dossier-redaction/10 px-3 py-2 text-xs text-dossier-redaction">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 border-t border-dossier-paperEdge pt-4">
            <button
              type="button"
              onClick={() => setConfirmOpen(false)}
              disabled={pending}
              className="rounded px-3 py-1.5 font-case text-[10px] uppercase tracking-widest text-dossier-ink/50 transition-colors hover:bg-dossier-paperEdge/50 hover:text-dossier-ink disabled:opacity-50"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => void handleSplit()}
              disabled={!reasonValid || pending || !canMutate}
              title={!canMutate ? "Read-only role" : undefined}
              className="rounded border border-cyber-orange/60 bg-cyber-orange/15 px-4 py-1.5 font-case text-[10px] font-semibold uppercase tracking-widest text-cyber-orange transition-all hover:bg-cyber-orange/30 hover:shadow-[0_0_20px_rgba(255,107,53,0.35)] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-cyber-orange/15 disabled:hover:shadow-none"
            >
              {pending ? "Splitting…" : "Confirm split"}
            </button>
          </div>
        </div>
      </dialog>
    </>
  )
}
