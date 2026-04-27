"use client"

import { useState } from "react"
import { ActionClassificationBadge } from "../../components/ActionClassificationBadge"
import { ConfirmDialog } from "../../components/ConfirmDialog"
import { JsonBlock } from "../../components/JsonBlock"
import { RelativeTime } from "../../components/RelativeTime"
import { useToast } from "../../components/Toast"
import { ApiError, executeAction, revertAction, type ActionSummary } from "../../lib/api"
import { useCanMutate } from "../../lib/SessionContext"

interface ActionControlsProps {
  action: ActionSummary
  incidentId: string
  onMutated: () => void
}

function StatusChip({ status }: { status: string }) {
  const color =
    status === "executed"
      ? "border-emerald-800 bg-emerald-950 text-emerald-300"
      : status === "failed"
        ? "border-red-800 bg-red-950 text-red-300"
        : status === "partial"
          ? "border-amber-700 bg-amber-950 text-amber-300"
          : status === "reverted"
            ? "border-zinc-700 bg-zinc-800 text-zinc-400"
            : status === "skipped"
              ? "border-zinc-700 bg-zinc-800 text-zinc-500"
              : "border-zinc-700 bg-zinc-800 text-zinc-400"
  const title =
    status === "partial"
      ? "Action partially completed — DB state written, enforcement did not confirm. See action log."
      : undefined
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs ${color}`} title={title}>{status}</span>
  )
}

export function ActionControls({ action, incidentId, onMutated }: ActionControlsProps) {
  const { push } = useToast()
  const canMutate = useCanMutate()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [mode, setMode] = useState<"execute" | "revert">("execute")
  const [pending, setPending] = useState(false)
  const [inlineError, setInlineError] = useState<{ code: string; message: string } | null>(null)

  const openExecute = () => {
    setMode("execute")
    setInlineError(null)
    setDialogOpen(true)
  }
  const openRevert = () => {
    setMode("revert")
    setInlineError(null)
    setDialogOpen(true)
  }
  const closeDialog = () => {
    if (!pending) {
      setDialogOpen(false)
      setInlineError(null)
    }
  }

  const handleConfirm = async () => {
    setPending(true)
    setInlineError(null)
    try {
      if (mode === "execute") {
        await executeAction(action.id)
        push({ variant: "success", title: `Action ${action.kind.replace(/_/g, " ")} executed` })
      } else {
        await revertAction(action.id)
        push({ variant: "success", title: `Action ${action.kind.replace(/_/g, " ")} reverted` })
      }
      setDialogOpen(false)
      onMutated()
    } catch (err) {
      if (err instanceof ApiError) {
        setInlineError({ code: err.code, message: err.message })
      } else {
        setDialogOpen(false)
        push({ variant: "error", title: `Action ${mode} failed` })
      }
    } finally {
      setPending(false)
    }
  }

  const { status, classification } = action

  // Determine which button (if any) to show
  let actionButton: React.ReactNode = null
  if (status === "proposed") {
    if (classification === "auto_safe") {
      actionButton = (
        <span className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs text-zinc-500 cursor-default">
          auto-executing…
        </span>
      )
    } else if (classification === "suggest_only") {
      actionButton = (
        <span
          title="This action is suggest_only and cannot be executed from the lab UI."
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs text-zinc-500 cursor-default"
        >
          Not executable in lab
        </span>
      )
    } else if (classification === "reversible" || classification === "disruptive") {
      actionButton = (
        <button
          onClick={openExecute}
          disabled={!canMutate}
          title={!canMutate ? "Read-only role" : undefined}
          className={`rounded px-2.5 py-0.5 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
            classification === "disruptive"
              ? "bg-red-900 text-red-200 hover:bg-red-800"
              : "bg-indigo-800 text-indigo-100 hover:bg-indigo-700"
          }`}
        >
          Execute
        </button>
      )
    }
  } else if (status === "executed" && classification === "reversible") {
    actionButton = (
      <button
        onClick={openRevert}
        disabled={!canMutate}
        title={!canMutate ? "Read-only role" : undefined}
        className="rounded px-2.5 py-0.5 text-xs font-medium bg-zinc-700 text-zinc-200 hover:bg-zinc-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Revert
      </button>
    )
  }

  const dialogTitle = mode === "execute"
    ? `Execute: ${action.kind.replace(/_/g, " ")}`
    : `Revert: ${action.kind.replace(/_/g, " ")}`

  const dialogBody = (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <ActionClassificationBadge classification={action.classification} />
        <StatusChip status={action.status} />
        {action.proposed_by === "system" && (
          <span className="rounded border border-indigo-800 bg-indigo-950 px-1.5 py-0.5 text-xs text-indigo-300">
            system
          </span>
        )}
      </div>
      {action.classification_reason && (
        <p className="text-xs text-zinc-400">{action.classification_reason}</p>
      )}
      <div>
        <p className="text-xs text-zinc-500 mb-1">Params</p>
        <JsonBlock data={action.params} />
      </div>
      {mode === "revert" && action.last_log?.reason && (
        <p className="text-xs text-zinc-400">
          Execution note: {action.last_log.reason}
        </p>
      )}
    </div>
  )

  return (
    <>
      <div className="mt-2 flex flex-col gap-2">
        {/* Classification reason sentence */}
        {action.classification_reason && (
          <p className="text-xs text-zinc-500">{action.classification_reason}</p>
        )}

        {/* Log entry (last_log only — TODO(phase-6): render full log thread when backend adds GET /v1/responses/{id}/logs) */}
        {action.last_log && (
          <div className="rounded border border-zinc-800 bg-zinc-900/50 px-2.5 py-2 text-xs text-zinc-500 space-y-0.5">
            <div className="flex flex-wrap gap-2 items-center">
              <span
                className={`rounded px-1.5 py-0.5 text-xs border ${
                  action.last_log.result === "ok"
                    ? "border-emerald-800 bg-emerald-950 text-emerald-300"
                    : action.last_log.result === "fail"
                      ? "border-red-800 bg-red-950 text-red-300"
                      : action.last_log.result === "partial"
                        ? "border-amber-700 bg-amber-950 text-amber-300"
                        : "border-zinc-700 bg-zinc-800 text-zinc-400"
                }`}
              >
                {action.last_log.result}
              </span>
              <span>{action.last_log.executed_by}</span>
              <RelativeTime at={action.last_log.executed_at} />
            </div>
            {action.last_log.reason && (
              <p className="text-zinc-600">{action.last_log.reason}</p>
            )}
            {action.last_log.reversal_info &&
              typeof action.last_log.reversal_info.ar_dispatch_status === "string" && (
              <p className="text-zinc-500">
                Active Response:{" "}
                <span className={
                  action.last_log.reversal_info.ar_dispatch_status === "dispatched"
                    ? "text-emerald-400"
                    : action.last_log.reversal_info.ar_dispatch_status === "failed" ||
                      action.last_log.reversal_info.ar_dispatch_status === "skipped"
                      ? "text-amber-400"
                      : "text-zinc-400"
                }>
                  {action.last_log.reversal_info.ar_dispatch_status as string}
                </span>
                {action.last_log.reversal_info.error != null && (
                  <span className="text-zinc-600"> ({action.last_log.reversal_info.error as string})</span>
                )}
              </p>
            )}
          </div>
        )}

        {/* Button + terminal status */}
        {actionButton && <div className="flex">{actionButton}</div>}
        {["failed", "skipped"].includes(status) && action.last_log?.reason && (
          <p className="text-xs text-zinc-500">{action.last_log.reason}</p>
        )}
      </div>

      <ConfirmDialog
        open={dialogOpen}
        title={dialogTitle}
        body={dialogBody}
        confirmLabel={mode === "execute" ? "Execute" : "Revert"}
        danger={action.classification === "disruptive" && mode === "execute"}
        requireTypedConfirmation={
          action.classification === "disruptive" && mode === "execute"
            ? incidentId
            : undefined
        }
        pending={pending}
        error={inlineError}
        onConfirm={handleConfirm}
        onClose={closeDialog}
      />
    </>
  )
}
