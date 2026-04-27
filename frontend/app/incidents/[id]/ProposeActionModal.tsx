"use client"

import { useEffect, useRef, useState } from "react"
import { ApiError, listLabAssets, proposeAction, type ActionKind, type LabAsset, type LabAssetKind } from "../../lib/api"
import { ACTION_FORMS, ENABLED_KINDS, type FieldDef } from "../../lib/actionForms"
import { useToast } from "../../components/Toast"
import { useCanMutate } from "../../lib/SessionContext"

interface ProposeActionModalProps {
  open: boolean
  incidentId: string
  onClose: () => void
  onProposed: () => void
}

// Module-level cache so datalist hints survive re-opens without refetching
const labAssetCache = new Map<LabAssetKind, LabAsset[]>()

export function ProposeActionModal({ open, incidentId, onClose, onProposed }: ProposeActionModalProps) {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<Element | null>(null)

  const [kind, setKind] = useState<ActionKind>(ENABLED_KINDS[0])
  const [form, setForm] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)
  const [scopeError, setScopeError] = useState<string | null>(null)
  const [labAssets, setLabAssets] = useState<LabAsset[]>([])

  const formDef = ACTION_FORMS[kind]

  // Open / close native dialog
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open) {
      returnFocusRef.current = document.activeElement
      dialog.showModal()
    } else {
      dialog.close()
      const el = returnFocusRef.current
      if (el instanceof HTMLElement) el.focus()
    }
  }, [open])

  // Reset form when kind changes
  useEffect(() => {
    setForm({})
    setScopeError(null)
  }, [kind])

  // Fetch lab assets when a select-lab-asset field is in the form def
  useEffect(() => {
    if (!open) return
    const field = formDef.fields.find((f) => f.kind === "select-lab-asset")
    if (!field?.labAssetKind) return
    const assetKind = field.labAssetKind
    if (labAssetCache.has(assetKind)) {
      setLabAssets(labAssetCache.get(assetKind)!)
      return
    }
    listLabAssets({ kind: assetKind })
      .then((assets) => {
        labAssetCache.set(assetKind, assets)
        setLabAssets(assets)
      })
      .catch(() => {/* non-critical; input still works without datalist */})
  }, [open, kind, formDef.fields])

  const setField = (name: string, value: string) => {
    setForm((prev) => ({ ...prev, [name]: value }))
    setScopeError(null)
  }

  const validate = () => {
    for (const field of formDef.fields) {
      if (field.required && !form[field.name]?.trim()) return false
    }
    return true
  }

  const handleSubmit = async () => {
    if (!validate() || pending) return
    setPending(true)
    setScopeError(null)
    try {
      await proposeAction({
        incident_id: incidentId,
        kind,
        params: formDef.buildParams(form),
      })
      push({ variant: "success", title: `Action ${kind.replace(/_/g, " ")} proposed` })
      onProposed()
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.code === "out_of_lab_scope") {
        setScopeError(err.message)
      } else {
        const message = err instanceof ApiError ? err.message : "Failed to propose action"
        push({ variant: "error", title: "Propose failed", body: message })
        onClose()
      }
    } finally {
      setPending(false)
    }
  }

  const renderField = (field: FieldDef) => {
    const value = form[field.name] ?? ""
    const listId = field.kind === "select-lab-asset" ? `datalist-${field.name}` : undefined

    return (
      <div key={field.name} className="space-y-1">
        <label className="text-xs text-zinc-400">
          {field.label}
          {field.required && <span className="ml-1 text-red-400">*</span>}
        </label>

        {field.kind === "select" ? (
          <select
            value={value}
            onChange={(e) => setField(field.name, e.target.value)}
            disabled={pending}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-zinc-500 disabled:opacity-50"
          >
            <option value="">— select —</option>
            {field.options?.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        ) : (
          <>
            <input
              type="text"
              value={value}
              onChange={(e) => setField(field.name, e.target.value)}
              disabled={pending}
              placeholder={field.placeholder}
              list={listId}
              autoComplete="off"
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 disabled:opacity-50"
            />
            {listId && labAssets.length > 0 && (
              <datalist id={listId}>
                {labAssets.map((a) => (
                  <option key={a.id} value={a.natural_key} />
                ))}
              </datalist>
            )}
          </>
        )}

        {field.help && <p className="text-xs text-zinc-600">{field.help}</p>}
      </div>
    )
  }

  return (
    <dialog
      ref={dialogRef}
      onCancel={(e) => { e.preventDefault(); if (!pending) onClose() }}
      className="backdrop:bg-black/60 bg-transparent p-0 m-auto rounded-xl shadow-2xl outline-none max-w-md w-full"
    >
      <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-5 flex flex-col gap-4">
        <h2 className="text-base font-semibold text-zinc-50">Propose action</h2>

        {/* Kind selector */}
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Action kind</label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as ActionKind)}
            disabled={pending}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-zinc-500 disabled:opacity-50"
          >
            {(Object.keys(ACTION_FORMS) as ActionKind[]).map((k) => (
              <option key={k} value={k} disabled={!ACTION_FORMS[k].enabled}>
                {ACTION_FORMS[k].label}
              </option>
            ))}
          </select>
        </div>

        {/* Kind-specific fields */}
        {formDef.fields.map(renderField)}

        {/* Out-of-lab-scope inline error (principle #5) */}
        {scopeError && (
          <div className="rounded border border-red-800 bg-red-950/60 px-3 py-2 text-xs text-red-300">
            Out of lab scope: {scopeError}. Register the asset in lab_assets or use a different target.
          </div>
        )}

        {/* Button row */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={pending}
            className="rounded px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSubmit()}
            disabled={!validate() || pending || !canMutate}
            title={!canMutate ? "Read-only role" : undefined}
            className="rounded bg-indigo-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {pending ? "Proposing…" : "Propose"}
          </button>
        </div>
      </div>
    </dialog>
  )
}
