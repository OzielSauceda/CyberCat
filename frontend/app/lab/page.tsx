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

const kindStyles: Record<LabAssetKind, string> = {
  user: "text-indigo-300 bg-indigo-950 border-indigo-800",
  host: "text-violet-300 bg-violet-950 border-violet-800",
  ip: "text-cyan-300 bg-cyan-950 border-cyan-800",
  observable: "text-pink-300 bg-pink-950 border-pink-800",
}

function LabSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  )
}

interface AddAssetFormProps {
  onAdded: () => void
  canMutate: boolean
}

function AddAssetForm({ onAdded, canMutate }: AddAssetFormProps) {
  const { push } = useToast()
  const [kind, setKind] = useState<LabAssetKind>("host")
  const [naturalKey, setNaturalKey] = useState("")
  const [notes, setNotes] = useState("")
  const [pending, setPending] = useState(false)

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

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
      <div className="space-y-1">
        <label className="text-xs text-zinc-400">Kind</label>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as LabAssetKind)}
          disabled={pending}
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-indigo-600 disabled:opacity-50"
        >
          {ALL_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-zinc-400">
          Natural key <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={naturalKey}
          onChange={(e) => setNaturalKey(e.target.value)}
          disabled={pending}
          placeholder={kind === "user" ? "alice@corp.local" : kind === "host" ? "lab-win10-01" : kind === "ip" ? "203.0.113.7" : "observable-key"}
          autoComplete="off"
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm font-mono text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-600 disabled:opacity-50"
        />
      </div>

      <div className="space-y-1">
        <label className="text-xs text-zinc-400">Notes (optional)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={pending}
          rows={2}
          placeholder="Description or context…"
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-600 disabled:opacity-50 resize-none"
        />
      </div>

      <button
        type="submit"
        disabled={!canSubmit || !canMutate}
        title={!canMutate ? "Read-only role" : undefined}
        className="w-full rounded bg-indigo-700 py-1.5 text-sm font-medium text-white hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {pending ? "Registering…" : "Register asset"}
      </button>
    </form>
  )
}

export default function LabPage() {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const [kindFilter, setKindFilter] = useState<LabAssetKind | "">("")
  const [deleteTarget, setDeleteTarget] = useState<LabAsset | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [deleteError, setDeleteError] = useState<{ code: string; message: string } | null>(null)

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
      const msg = err instanceof ApiError ? err.message : "Failed to remove asset"
      const code = err instanceof ApiError ? err.code : "error"
      setDeleteError({ code, message: msg })
    } finally {
      setDeletePending(false)
    }
  }

  const filtered = assets ?? []

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Lab Assets</h1>
        <p className="mt-0.5 text-sm text-zinc-500">
          Only assets listed here can be targeted by automated response actions. Nothing outside this list gets touched.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Left: asset list */}
        <div>
          {/* Kind filter */}
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className="text-xs text-zinc-500">Filter:</span>
            {(["", ...ALL_KINDS] as const).map((k) => (
              <button
                key={k || "all"}
                onClick={() => setKindFilter(k as LabAssetKind | "")}
                className={`rounded-full border px-2.5 py-0.5 text-xs capitalize transition-colors ${
                  kindFilter === k
                    ? "border-indigo-700 bg-indigo-950 text-indigo-300"
                    : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {k || "all"}
              </button>
            ))}
          </div>

          {error && !assets && (
            <ErrorState error={error} onRetry={refetch} />
          )}

          {loading && !assets ? (
            <LabSkeleton />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="No assets registered"
              hint={kindFilter ? "No assets match this kind filter." : "Use the form on the right to add users, hosts, IPs, or observables you want CyberCat to be able to act on."}
            />
          ) : (
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900">
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Kind</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Natural key</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Notes</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">Registered</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((asset, i) => (
                    <tr
                      key={asset.id}
                      className={`border-b border-zinc-800 last:border-0 ${
                        i % 2 === 0 ? "bg-zinc-950" : "bg-zinc-900/40"
                      }`}
                    >
                      <td className="px-4 py-3">
                        <span
                          className={`rounded border px-1.5 py-0.5 font-mono text-xs ${
                            kindStyles[asset.kind as LabAssetKind]
                          }`}
                        >
                          {asset.kind}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-zinc-200">
                        {asset.natural_key}
                      </td>
                      <td className="px-4 py-3 text-xs text-zinc-500 max-w-[200px] truncate">
                        {asset.notes ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-zinc-500">
                        <RelativeTime at={asset.registered_at} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => {
                            setDeleteError(null)
                            setDeleteTarget(asset)
                          }}
                          disabled={!canMutate}
                          title={!canMutate ? "Read-only role" : undefined}
                          className="text-xs text-zinc-500 hover:text-red-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: add form */}
        <div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
            <h2 className="mb-4 text-sm font-semibold text-zinc-200">Register asset</h2>
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
