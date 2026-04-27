interface PanelProps {
  title: string
  count?: number
  children: React.ReactNode
  className?: string
  headerAction?: React.ReactNode
}

export function Panel({ title, count, children, className = "", headerAction }: PanelProps) {
  return (
    <section className={`rounded-lg border border-zinc-800 bg-zinc-900 ${className}`}>
      <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          {title}
        </h2>
        {count != null && (
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
            {count}
          </span>
        )}
        {headerAction && <div className="ml-auto">{headerAction}</div>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}
