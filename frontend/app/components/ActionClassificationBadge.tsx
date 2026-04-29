import type { ActionClassification } from "../lib/api"

const config: Record<ActionClassification, { label: string; classes: string }> = {
  auto_safe: {
    label: "auto-safe",
    classes: "text-emerald-300 bg-emerald-950 border-emerald-800",
  },
  suggest_only: {
    label: "suggest",
    classes: "text-sky-300 bg-sky-950 border-sky-800",
  },
  reversible: {
    label: "reversible",
    classes: "text-amber-300 bg-amber-950 border-amber-800",
  },
  disruptive: {
    label: "disruptive",
    classes: "text-red-300 bg-red-950 border-red-700",
  },
}

export function ActionClassificationBadge({
  classification,
}: {
  classification: ActionClassification
}) {
  const { label, classes } = config[classification]
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-case font-medium uppercase tracking-widest ${classes}`}
    >
      {label}
    </span>
  )
}
