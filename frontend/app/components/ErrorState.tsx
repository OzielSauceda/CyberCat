interface ErrorStateProps {
  error: Error
  onRetry?: () => void
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div className="rounded-lg border border-red-900 bg-red-950/40 p-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-red-400 font-bold text-sm select-none" aria-hidden>
          !
        </span>
        <div className="flex-1">
          <p className="text-sm font-medium text-red-300">Something went wrong</p>
          <p className="mt-0.5 text-xs text-red-400">{error.message}</p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="shrink-0 rounded border border-red-800 bg-red-950 px-2.5 py-1 text-xs text-red-300 hover:bg-red-900 transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
