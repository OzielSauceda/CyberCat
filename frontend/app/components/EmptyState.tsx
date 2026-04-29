interface EmptyStateProps {
  title: string
  hint?: string
  action?: React.ReactNode
}

export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <span className="font-mono text-xs text-dossier-evidenceTape/20 select-none tracking-[0.5em]" aria-hidden>
        / / NULL / /
      </span>
      <p className="font-case text-sm font-semibold uppercase tracking-wider text-dossier-ink/60">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-relaxed text-dossier-ink/40">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
