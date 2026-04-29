function barColor(value: number): string {
  if (value >= 0.8) return "bg-emerald-500"
  if (value >= 0.5) return "bg-amber-500"
  return "bg-red-500"
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <span className="inline-flex items-center gap-1.5" title={`Confidence: ${pct}%`}>
      <span className="relative h-1.5 w-16 overflow-hidden rounded-full bg-zinc-700">
        <span
          className={`absolute inset-y-0 left-0 rounded-full transition-all ${barColor(value)}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="text-xs tabular-nums text-dossier-ink/70">{pct}%</span>
    </span>
  )
}
