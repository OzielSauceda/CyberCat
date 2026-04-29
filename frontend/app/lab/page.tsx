"use client"

import { useCallback, useState } from "react"
import { ConfirmDialog } from "../components/ConfirmDialog"
import { EmptyState } from "../components/EmptyState"
import { ErrorState } from "../components/ErrorState"
import { RelativeTime } from "../components/RelativeTime"
import { SkeletonRow } from "../components/Skeleton"
import { useToast } from "../components/Toast"
import {
  ApiError,
  createLabAsset,
  deleteLabAsset,
  listLabAssets,
  type LabAsset,
  type LabAssetIn,
  type LabAssetKind,
} from "../lib/api"
import { useCanMutate } from "../lib/SessionContext"
import { usePolling } from "../lib/usePolling"

const ALL_KINDS: LabAssetKind[] = ["user", "host", "ip", "observable"]

const KIND_STYLE: Record<LabAssetKind, { text: string; border: string; bg: string }> = {
  user:       { text: "#818cf8", border: "#4f46e540", bg: "#1e1b4b25" },
  host:       { text: "#a78bfa", border: "#7c3aed40", bg: "#2e106525" },
  ip:         { text: "#00d4ff", border: "#00d4ff40", bg: "#00d4ff0f" },
  observable: { text: "#f472b6", border: "#db277740", bg: "#83184320" },
}

function LabSkeleton() {
  return (
    <div className="space-y-1.5">
      {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
    </div>
  )
}

// ── Register form ─────────────────────────────────────────────────────────────

interface AddAssetFormProps {
  onAdded: () => void
  canMutate: boolean
}

function AddAssetForm({ onAdded, canMutate }: AddAssetFormProps) {
  const { push } = useToast()
  const [kind,       setKind]       = useState<LabAssetKind>("host")
  const [naturalKey, setNaturalKey] = useState("")
  const [notes,      setNotes]      = useState("")
  const [pending,    setPending]    = useState(false)

  const canSubmit = naturalKey.trim().length > 0 && !pending

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setPending(true)
    try {
      const body: LabAssetIn = {
        kind,
        natural_key: naturalKey.trim(),
        notes: notes.trim() || undefined,
      }
      await createLabAsset(body)
      push({ variant: "success", title: `Registered ${kind}:${naturalKey.trim()}` })
      setNaturalKey("")
      setNotes("")
      onAdded()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        push({ variant: "error", title: "Already registered", body: err.message })
      } else {
        const msg = err instanceof ApiError ? err.message : "Failed to register asset"
        push({ variant: "error", title: "Registration failed", body: msg })
      }
    } finally {
      setPending(false)
    }
  }

  const fieldClass =
    "w-full border border-dossier-paperEdge bg-dossier-stamp px-3 py-2 font-mono text-sm text-dossier-ink/80 placeholder-dossier-ink/20 outline-none focus:border-dossier-evidenceTape/50 transition-colors disabled:opacity-50"

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
      <div className="space-y-1">
        <label className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/35">Kind</label>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as LabAssetKind)}
          disabled={pending}
          className={fieldClass}
        >
          {ALL_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>

      <div className="space-y-1">
        <label className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/35">
          Natural key <span className="text-dossier-redaction">*</span>
        </label>
        <input
          type="text"
          value={naturalKey}
          onChange={(e) => setNaturalKey(e.target.value)}
          disabled={pending}
          placeholder={
            kind === "user" ? "alice@corp.local" :
            kind === "host" ? "lab-win10-01" :
            kind === "ip"   ? "203.0.113.7" : "observable-key"
          }
          autoComplete="off"
          className={fieldClass}
        />
      </div>

      <div className="space-y-1">
        <label className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/35">Notes (optional)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={pending}
          rows={2}
          placeholder="Description or context…"
          className={`${fieldClass} resize-none`}
        />
      </div>

      <button
        type="submit"
        disabled={!canSubmit || !canMutate}
        title={!canMutate ? "Read-only role" : undefined}
        className="w-full py-2 font-case text-xs font-semibold uppercase tracking-widest border border-dossier-evidenceTape/25 text-dossier-evidenceTape/65 hover:border-dossier-evidenceTape/55 hover:text-dossier-evidenceTape hover:bg-dossier-evidenceTape/5 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
      >
        {pending ? "Registering…" : "Register asset"}
      </button>
    </form>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LabPage() {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const [kindFilter,    setKindFilter]    = useState<LabAssetKind | "">("")
  const [deleteTarget,  setDeleteTarget]  = useState<LabAsset | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [deleteError,   setDeleteError]   = useState<{ code: string; message: string } | null>(null)

  const fetcher = useCallback(
    () => listLabAssets(kindFilter ? { kind: kindFilter } : undefined),
    [kindFilter],
  )

  const { data: assets, error, loading, refetch } = usePolling(fetcher, 15_000)

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeletePending(true)
    setDeleteError(null)
    try {
      await deleteLabAsset(deleteTarget.id)
      push({ variant: "success", title: `Removed ${deleteTarget.kind}:${deleteTarget.natural_key}` })
      setDeleteTarget(null)
      refetch()
    } catch (err) {
      const msg  = err instanceof ApiError ? err.message : "Failed to remove asset"
      const code = err instanceof ApiError ? err.code    : "error"
      setDeleteError({ code, message: msg })
    } finally {
      setDeletePending(false)
    }
  }

  const filtered = assets ?? []

  return (
    <div className="space-y-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div>
        <h1 className="font-case text-2xl font-bold uppercase tracking-wider text-dossier-ink">
          Lab Environment
        </h1>
        <p className="mt-0.5 font-mono text-xs text-dossier-ink/30">
          Only assets registered here can be targeted by automated response actions.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">

        {/* ── Asset list ──────────────────────────────────────────────────── */}
        <div className="space-y-3">

          {/* Kind filter chips */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 mr-1">kind</span>
            {(["", ...ALL_KINDS] as const).map((k) => {
              const active = kindFilter === k
              const color  = k ? KIND_STYLE[k as LabAssetKind].text : "#cdd6df"
              return (
                <button
                  key={k || "all"}
                  onClick={() => setKindFilter(k as LabAssetKind | "")}
                  className="px-2.5 py-1 font-case text-[11px] font-semibold uppercase tracking-wide border transition-all duration-150"
                  style={{
                    borderColor: active ? `${color}55` : "#0c1b2e",
                    background:  active ? `${color}12` : "transparent",
                    color:       active ? color : "#cdd6df28",
                  }}
                >
                  {k || "all"}
                </button>
              )
            })}
          </div>

          {error && !assets && <ErrorState error={error} onRetry={refetch} />}

          {loading && !assets ? (
            <LabSkeleton />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="No assets registered"
              hint={
                kindFilter
                  ? "No assets match this kind filter."
                  : "Use the form to add users, hosts, IPs, or observables that CyberCat can act on."
              }
            />
          ) : (
            <div className="border border-dossier-paperEdge overflow-hidden">
              {/* Column headers */}
              <div className="flex items-center gap-4 px-4 py-2 border-b border-dossier-paperEdge bg-dossier-stamp">
                <span className="w-24 shrink-0 font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25">Kind</span>
                <span className="flex-1 font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25">Natural key</span>
                <span className="w-40 shrink-0 font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 hidden md:block">Notes</span>
                <span className="w-28 shrink-0 font-mono text-[11px] uppercase tracking-widest text-dossier-ink/25 hidden lg:block">Registered</span>
                <span className="w-14 shrink-0" />
              </div>

              {filtered.map((asset) => {
                const ks = KIND_STYLE[asset.kind as LabAssetKind]
                return (
                  <div
                    key={asset.id}
                    className="flex items-center gap-4 px-4 py-3 border-b border-dossier-paperEdge/40 last:border-0 hover:bg-dossier-paperEdge/20 transition-colors"
                  >
                    <span
                      className="w-24 shrink-0 font-mono text-xs px-1.5 py-0.5 border w-fit"
                      style={{ color: ks.text, borderColor: ks.border, background: ks.bg }}
                    >
                      {asset.kind}
                    </span>
                    <span className="flex-1 font-mono text-sm text-dossier-ink/80 truncate min-w-0">
                      {asset.natural_key}
                    </span>
                    <span className="w-40 shrink-0 font-mono text-xs text-dossier-ink/30 truncate hidden md:block">
                      {asset.notes ?? "—"}
                    </span>
                    <span className="w-28 shrink-0 font-mono text-xs text-dossier-ink/25 hidden lg:block">
                      <RelativeTime at={asset.registered_at} />
                    </span>
                    <button
                      onClick={() => { setDeleteError(null); setDeleteTarget(asset) }}
                      disabled={!canMutate}
                      title={!canMutate ? "Read-only role" : undefined}
                      className="w-14 shrink-0 font-mono text-xs text-dossier-ink/20 hover:text-dossier-redaction transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-right"
                    >
                      remove
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Register form ────────────────────────────────────────────────── */}
        <div>
          <div className="border border-dossier-paperEdge bg-dossier-stamp p-5">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-[2px] h-4 bg-dossier-evidenceTape" />
              <h2 className="font-case text-[13px] font-semibold uppercase tracking-widest text-dossier-evidenceTape">
                Register asset
              </h2>
            </div>
            <AddAssetForm onAdded={refetch} canMutate={canMutate} />
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Remove ${deleteTarget?.kind}:${deleteTarget?.natural_key}?`}
        body="Any automated actions targeting this asset will stop working once it's removed."
        confirmLabel="Remove"
        danger
        pending={deletePending}
        error={deleteError}
        onConfirm={handleDelete}
        onClose={() => {
          if (!deletePending) {
            setDeleteTarget(null)
            setDeleteError(null)
          }
        }}
      />
    </div>
  )
}
