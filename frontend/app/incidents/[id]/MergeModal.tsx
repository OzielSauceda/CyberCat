"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import {
  ApiError,
  listIncidents,
  mergeIncidentInto,
  type IncidentSummary,
} from "../../lib/api"
import { useToast } from "../../components/Toast"
import { useCanMutate } from "../../lib/SessionContext"

interface MergeModalProps {
  open: boolean
  source: { id: string; title: string; kind: string }
  onClose: () => void
}

/**
 * MergeModal — fold this incident (the source) into a different, existing
 * incident (the target). On success, the operator is redirected to the
 * target incident page.
 *
 * Per ADR-0015, merge is operator-initiated; the platform never auto-merges.
 *
 * Aesthetic: the dossier "case-merge" stamp — a folder being pressed into
 * another. All surfaces use dossier tokens; the confirm button glows
 * cyber-orange (the "evidence tape" of a destructive-but-reversible action).
 */
export function MergeModal({ open, source, onClose }: MergeModalProps) {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const router = useRouter()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<Element | null>(null)

  const [candidates, setCandidates] = useState<IncidentSummary[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [search, setSearch] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [reason, setReason] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Open / close native dialog and reset state
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open) {
      returnFocusRef.current = document.activeElement
      dialog.showModal()
      setSearch("")
      setSelectedId(null)
      setReason("")
      setError(null)
    } else {
      dialog.close()
      const el = returnFocusRef.current
      if (el instanceof HTMLElement) el.focus()
    }
  }, [open])

  // Load merge candidates when the modal opens. Fetch the most recent open
  // incidents and filter out the source itself + already-merged/closed.
  useEffect(() => {
    if (!open) return
    setLoadingCandidates(true)
    listIncidents({ limit: 50 })
      .then((list) => {
        const eligible = list.items.filter(
          (i) =>
            i.id !== source.id &&
            i.status !== "merged" &&
            i.status !== "closed",
        )
        setCandidates(eligible)
      })
      .catch(() => {
        push({ variant: "error", title: "Couldn't load merge candidates" })
      })
      .finally(() => setLoadingCandidates(false))
  }, [open, source.id, push])

  const filtered = search.trim()
    ? candidates.filter((c) => {
        const q = search.toLowerCase()
        return (
          c.title.toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q) ||
          (c.primary_user ?? "").toLowerCase().includes(q) ||
          (c.primary_host ?? "").toLowerCase().includes(q)
        )
      })
    : candidates

  const selected = candidates.find((c) => c.id === selectedId) ?? null
  const reasonValid = reason.trim().length >= 1 && reason.length <= 500

  const handleMerge = async () => {
    if (!selectedId || !reasonValid || pending) return
    setPending(true)
    setError(null)
    try {
      const target = await mergeIncidentInto(source.id, {
        target_id: selectedId,
        reason: reason.trim(),
      })
      push({
        variant: "success",
        title: "Incident merged",
        body: `Folded into ${target.title}`,
      })
      onClose()
      router.push(`/incidents/${target.id}`)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Merge failed"
      setError(message)
    } finally {
      setPending(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      onCancel={(e) => {
        e.preventDefault()
        if (!pending) onClose()
      }}
      className="m-auto w-full max-w-2xl rounded-xl bg-transparent p-0 outline-none backdrop:bg-dossier-stamp/85 backdrop:backdrop-blur-sm"
    >
      <div
        className="flex flex-col gap-5 rounded-xl border border-dossier-paperEdge bg-dossier-paper p-6 shadow-dossier"
        style={{ boxShadow: "inset 0 0 60px rgba(0,212,255,0.025), 0 0 0 1px rgba(0,212,255,0.07), 0 12px 48px rgba(0,0,0,0.85)" }}
      >
        {/* "stamp" header */}
        <div className="flex items-start justify-between gap-4 border-b border-dossier-paperEdge pb-4">
          <div>
            <p className="font-case text-[9px] font-semibold uppercase tracking-[0.25em] text-cyber-orange">
              Case file action — merge
            </p>
            <h2 className="mt-1 text-base font-semibold text-dossier-ink">
              Fold this incident into another
            </h2>
            <p className="mt-1 text-xs text-dossier-ink/50">
              Source:{" "}
              <span className="font-mono text-dossier-evidenceTape/80">
                INC-{source.id.slice(-8).toUpperCase()}
              </span>{" "}
              · {source.title}
            </p>
          </div>
          <span
            className="select-none border-2 border-cyber-orange/40 px-2 py-0.5 font-case text-[9px] uppercase tracking-widest text-cyber-orange/70"
            style={{ transform: "rotate(-3deg)" }}
          >
            destructive
          </span>
        </div>

        {/* Search */}
        <div className="space-y-1.5">
          <label className="font-case text-[10px] font-semibold uppercase tracking-widest text-dossier-ink/60">
            Pick the target incident
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={pending}
            placeholder="Filter by title, ID, user, or host…"
            className="w-full rounded border border-dossier-paperEdge bg-dossier-stamp px-3 py-2 text-sm text-dossier-ink placeholder-dossier-ink/30 outline-none transition-colors focus:border-dossier-evidenceTape/60 disabled:opacity-50"
          />
        </div>

        {/* Candidate list */}
        <div className="max-h-64 overflow-y-auto rounded border border-dossier-paperEdge bg-dossier-stamp">
          {loadingCandidates ? (
            <div className="px-4 py-6 text-center font-case text-[10px] uppercase tracking-widest text-dossier-ink/40">
              Loading candidates…
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs text-dossier-ink/40">
              {candidates.length === 0
                ? "No other open incidents to merge into."
                : "No matches for that filter."}
            </div>
          ) : (
            <ul className="divide-y divide-dossier-paperEdge">
              {filtered.map((c) => {
                const isSelected = c.id === selectedId
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(c.id)}
                      disabled={pending}
                      className={`flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors ${
                        isSelected
                          ? "bg-dossier-evidenceTape/10"
                          : "hover:bg-dossier-paperEdge/40"
                      }`}
                    >
                      <span
                        className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${
                          isSelected
                            ? "bg-dossier-evidenceTape ring-2 ring-dossier-evidenceTape/30"
                            : "bg-dossier-paperEdge"
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[9px] tracking-widest text-dossier-evidenceTape/50">
                            INC-{c.id.slice(-8).toUpperCase()}
                          </span>
                          <span
                            className={`font-case text-[8px] uppercase tracking-widest ${
                              c.severity === "critical"
                                ? "text-dossier-redaction"
                                : c.severity === "high"
                                ? "text-cyber-orange"
                                : c.severity === "medium"
                                ? "text-cyber-yellow"
                                : "text-dossier-ink/40"
                            }`}
                          >
                            {c.severity}
                          </span>
                          <span className="font-mono text-[9px] text-dossier-ink/30">·</span>
                          <span className="font-mono text-[9px] uppercase tracking-widest text-dossier-ink/35">
                            {c.status}
                          </span>
                        </div>
                        <p className="mt-0.5 truncate text-sm text-dossier-ink">{c.title}</p>
                        {(c.primary_user || c.primary_host) && (
                          <p className="mt-0.5 font-mono text-[10px] text-dossier-ink/40">
                            {[c.primary_user, c.primary_host].filter(Boolean).join(" · ")}
                          </p>
                        )}
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Selected target preview — dossier-style "before/after" */}
        {selected && (
          <div className="grid grid-cols-2 gap-3 rounded border border-dossier-evidenceTape/25 bg-dossier-stamp/60 p-3">
            <div>
              <p className="font-case text-[9px] uppercase tracking-widest text-dossier-ink/40">
                Source (becomes merged)
              </p>
              <p className="mt-1 truncate text-xs text-dossier-ink/70">{source.title}</p>
            </div>
            <div className="border-l border-dossier-paperEdge pl-3">
              <p className="font-case text-[9px] uppercase tracking-widest text-cyber-orange/80">
                → Target (absorbs evidence)
              </p>
              <p className="mt-1 truncate text-xs text-dossier-ink">{selected.title}</p>
            </div>
          </div>
        )}

        {/* Reason */}
        <div className="space-y-1.5">
          <label className="font-case text-[10px] font-semibold uppercase tracking-widest text-dossier-ink/60">
            Reason for the merge <span className="text-dossier-redaction/70">*</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={pending}
            placeholder="e.g. duplicate of target — same alice, same workstation, opened 2 minutes apart"
            maxLength={500}
            rows={2}
            className="w-full resize-none rounded border border-dossier-paperEdge bg-dossier-stamp px-3 py-2 text-sm text-dossier-ink placeholder-dossier-ink/30 outline-none transition-colors focus:border-dossier-evidenceTape/60 disabled:opacity-50"
          />
          <p className="text-right font-mono text-[10px] text-dossier-ink/30">
            {reason.length} / 500
          </p>
        </div>

        {/* Inline error */}
        {error && (
          <div className="rounded border border-dossier-redaction/40 bg-dossier-redaction/10 px-3 py-2 text-xs text-dossier-redaction">
            {error}
          </div>
        )}

        {/* Buttons */}
        <div className="flex justify-end gap-2 border-t border-dossier-paperEdge pt-4">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded px-3 py-1.5 font-case text-[10px] uppercase tracking-widest text-dossier-ink/50 transition-colors hover:bg-dossier-paperEdge/50 hover:text-dossier-ink disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleMerge()}
            disabled={!selectedId || !reasonValid || pending || !canMutate}
            title={!canMutate ? "Read-only role" : undefined}
            className="rounded border border-cyber-orange/60 bg-cyber-orange/15 px-4 py-1.5 font-case text-[10px] font-semibold uppercase tracking-widest text-cyber-orange transition-all hover:bg-cyber-orange/30 hover:shadow-[0_0_20px_rgba(255,107,53,0.35)] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-cyber-orange/15 disabled:hover:shadow-none"
          >
            {pending ? "Folding…" : "Confirm merge"}
          </button>
        </div>
      </div>
    </dialog>
  )
}
