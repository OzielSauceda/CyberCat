interface PanelProps {
  title: string
  count?: number
  children: React.ReactNode
  className?: string
  headerAction?: React.ReactNode
}

export function Panel({ title, count, children, className = "", headerAction }: PanelProps) {
  return (
    <section className={`rounded-lg border border-dossier-paperEdge bg-dossier-paper shadow-dossier ${className}`}>
      <div className="flex items-center gap-2.5 border-b border-dossier-paperEdge px-4 py-3">
        <span className="h-1.5 w-1.5 rounded-full bg-dossier-evidenceTape/60" />
        <h2 className="text-[11px] font-case font-semibold uppercase tracking-widest text-dossier-evidenceTape">
          {title}
        </h2>
        {count != null && (
          <span className="ml-0.5 rounded border border-dossier-paperEdge bg-dossier-stamp px-2 py-0.5 font-mono text-[10px] text-dossier-ink/50">
            {count}
          </span>
        )}
        {headerAction && <div className="ml-auto">{headerAction}</div>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}
