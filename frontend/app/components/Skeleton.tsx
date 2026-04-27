export function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className="h-5 w-12 rounded bg-zinc-800" />
        <div className="h-5 w-20 rounded-full bg-zinc-800" />
        <div className="ml-auto h-4 w-24 rounded bg-zinc-800" />
      </div>
      <div className="mb-2 h-4 w-3/4 rounded bg-zinc-800" />
      <div className="h-4 w-1/2 rounded bg-zinc-800" />
      <div className="mt-4 flex gap-4">
        <div className="h-3 w-16 rounded bg-zinc-800" />
        <div className="h-3 w-16 rounded bg-zinc-800" />
        <div className="h-3 w-16 rounded bg-zinc-800" />
      </div>
    </div>
  )
}

export function SkeletonRow() {
  return (
    <div className="animate-pulse flex items-center gap-3 rounded p-2">
      <div className="h-4 w-32 rounded bg-zinc-800" />
      <div className="h-4 w-16 rounded bg-zinc-800" />
      <div className="h-4 flex-1 rounded bg-zinc-800" />
    </div>
  )
}
