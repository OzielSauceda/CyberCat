"use client"

import { useEffect, useRef, useState } from "react"
import { EmptyState } from "../../components/EmptyState"
import { Panel } from "../../components/Panel"
import { RelativeTime } from "../../components/RelativeTime"
import { useToast } from "../../components/Toast"
import { ApiError, createNote, type NoteRef } from "../../lib/api"
import { useCanMutate, useSession } from "../../lib/SessionContext"

interface NotesPanelProps {
  incidentId: string
  notes: NoteRef[]
  onNoteCreated: () => void
}

export function NotesPanel({ incidentId, notes, onNoteCreated }: NotesPanelProps) {
  const { push } = useToast()
  const { user } = useSession()
  const canMutate = useCanMutate()
  const [body, setBody] = useState("")
  const [pending, setPending] = useState(false)
  const [optimistic, setOptimistic] = useState<NoteRef[]>([])
  const counterRef = useRef(0)

  const trimmed = body.trim()
  const charCount = trimmed.length
  const canSubmit = charCount >= 1 && charCount <= 4000 && !pending && canMutate

  // Dedup: show temp only until the polled list contains it
  const displayNotes = [
    ...notes,
    ...optimistic.filter(
      (o) => !notes.some((n) => n.body === o.body && n.author === o.author),
    ),
  ]

  const submit = async () => {
    if (!canSubmit) return
    const tempId = `tmp-${counterRef.current++}`
    const tempNote: NoteRef = {
      id: tempId,
      body: trimmed,
      author: user?.email ?? "you",
      created_at: new Date().toISOString(),
    }
    setOptimistic((prev) => [...prev, tempNote])
    setBody("")
    setPending(true)

    // GC temp after 10s regardless
    const gcTimer = setTimeout(() => {
      setOptimistic((prev) => prev.filter((n) => n.id !== tempId))
    }, 10_000)

    try {
      await createNote(incidentId, { body: trimmed })
      onNoteCreated()
    } catch (err) {
      clearTimeout(gcTimer)
      setOptimistic((prev) => prev.filter((n) => n.id !== tempId))
      const message = err instanceof ApiError ? err.message : "Failed to save note"
      push({ variant: "error", title: "Note failed", body: message })
    } finally {
      setPending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault()
      void submit()
    }
  }

  const counterColor =
    charCount > 4000
      ? "text-red-400"
      : charCount > 3800
        ? "text-amber-400"
        : "text-zinc-600"

  return (
    <Panel title="Notes" count={displayNotes.length}>
      {displayNotes.length === 0 ? (
        <EmptyState title="No notes yet" hint="Analyst annotations will appear here." />
      ) : (
        <div className="space-y-3 mb-4">
          {displayNotes.map((n) => (
            <div
              key={n.id}
              className={`rounded-lg border bg-zinc-950 p-3 ${
                n.id.startsWith("tmp-") ? "border-zinc-700 opacity-70" : "border-zinc-800"
              }`}
            >
              <p className="mb-1 text-xs text-zinc-500">
                {n.author} · <RelativeTime at={n.created_at} />
                {n.id.startsWith("tmp-") && (
                  <span className="ml-2 text-zinc-600 italic">saving…</span>
                )}
              </p>
              <p className="text-sm text-zinc-200 whitespace-pre-wrap">{n.body}</p>
            </div>
          ))}
        </div>
      )}

      {/* Composer */}
      <div className="space-y-2">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          placeholder={canMutate ? "Add a note… (Ctrl+Enter to submit)" : "Read-only role — cannot post notes"}
          disabled={pending || !canMutate}
          title={!canMutate ? "Read-only role" : undefined}
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 disabled:opacity-50 resize-none"
        />
        <div className="flex items-center justify-between gap-2">
          <span className={`text-xs ${counterColor}`}>{charCount}/4000</span>
          <button
            onClick={() => void submit()}
            disabled={!canSubmit}
            title={!canMutate ? "Read-only role" : undefined}
            className="rounded bg-indigo-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {pending ? "Saving…" : "Post note"}
          </button>
        </div>
      </div>
    </Panel>
  )
}
