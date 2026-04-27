"use client"

import { useEffect, useRef, useState } from "react"
import clsx from "clsx"

export interface ConfirmDialogProps {
  open: boolean
  title: string
  body?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  requireTypedConfirmation?: string
  pending?: boolean
  error?: { code: string; message: string } | null
  onConfirm: () => void | Promise<void>
  onClose: () => void
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  requireTypedConfirmation,
  pending = false,
  error,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<Element | null>(null)
  const typedInputRef = useRef<HTMLInputElement>(null)
  const [typedValue, setTypedValue] = useState("")

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (open) {
      returnFocusRef.current = document.activeElement
      dialog.showModal()
      setTypedValue("")
      setTimeout(() => {
        if (typedInputRef.current) {
          typedInputRef.current.focus()
        } else {
          const first = dialog.querySelector<HTMLElement>(
            "button:not([disabled]), input:not([disabled]), textarea:not([disabled])",
          )
          first?.focus()
        }
      }, 0)
    } else {
      dialog.close()
      const el = returnFocusRef.current
      if (el instanceof HTMLElement) el.focus()
    }
  }, [open])

  // Close on backdrop click only when not danger
  const handleDialogClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (danger) return
    if (e.target === dialogRef.current) onClose()
  }

  const confirmDisabled =
    pending ||
    (requireTypedConfirmation !== undefined &&
      typedValue.trim() !== requireTypedConfirmation)

  return (
    <dialog
      ref={dialogRef}
      onCancel={(e) => { e.preventDefault(); if (!pending) onClose() }}
      onClick={handleDialogClick}
      className="backdrop:bg-black/60 bg-transparent p-0 m-auto rounded-xl shadow-2xl outline-none max-w-md w-full"
    >
      <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-5 flex flex-col gap-4">
        {/* Title */}
        <h2 className="text-base font-semibold text-zinc-50 leading-snug">{title}</h2>

        {/* Body */}
        {body && <div className="text-sm text-zinc-300 leading-relaxed">{body}</div>}

        {/* Typed confirmation input */}
        {requireTypedConfirmation !== undefined && (
          <div className="space-y-1">
            <p className="text-xs text-zinc-400">
              Type <span className="font-mono text-zinc-200">{requireTypedConfirmation}</span> to confirm:
            </p>
            <input
              ref={typedInputRef}
              type="text"
              value={typedValue}
              onChange={(e) => setTypedValue(e.target.value)}
              disabled={pending}
              autoComplete="off"
              spellCheck={false}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm font-mono text-zinc-100 outline-none focus:border-zinc-500 disabled:opacity-50"
            />
          </div>
        )}

        {/* Inline error */}
        {error && (
          <div className="rounded border border-red-800 bg-red-950/60 px-3 py-2 text-xs text-red-300">
            {error.message}
          </div>
        )}

        {/* Button row */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={pending}
            className="rounded px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-50 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={() => { void onConfirm() }}
            disabled={confirmDisabled}
            className={clsx(
              "rounded px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40",
              danger
                ? "bg-red-700 text-white hover:bg-red-600 disabled:bg-red-900"
                : "bg-indigo-700 text-white hover:bg-indigo-600 disabled:bg-indigo-900",
            )}
          >
            {pending ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  )
}
