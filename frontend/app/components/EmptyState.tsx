interface EmptyStateProps {
  title: string
  hint?: string
  action?: React.ReactNode
}

export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <span className="text-3xl text-zinc-700 select-none" aria-hidden>
        --
      </span>
      <p className="font-medium text-zinc-300">{title}</p>
      {hint && <p className="max-w-sm text-sm text-zinc-500">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
