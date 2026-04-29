"use client"

import { usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"
import { useSession } from "../lib/SessionContext"

const ROLE_LABELS: Record<string, string> = {
  admin: "ADMIN",
  analyst: "ANALYST",
  read_only: "READ-ONLY",
}

const ROLE_COLORS: Record<string, string> = {
  admin: "border-indigo-700/60 text-indigo-400/90",
  analyst: "border-emerald-800/60 text-emerald-500/90",
  read_only: "border-dossier-paperEdge text-dossier-ink/50",
}

export default function UserBadge() {
  const { user, status, authConfig, logout } = useSession()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (
      status === "anon" &&
      authConfig?.auth_required &&
      pathname !== "/login"
    ) {
      router.push(`/login?next=${encodeURIComponent(pathname)}`)
    }
  }, [status, authConfig, router, pathname])

  if (status === "loading") {
    return <span className="h-5 w-28 animate-pulse rounded bg-dossier-paperEdge/60" />
  }

  if (status === "anon" || !user) return null

  const roleLabel = ROLE_LABELS[user.role] ?? user.role.toUpperCase()
  const roleColor = ROLE_COLORS[user.role] ?? "border-dossier-paperEdge text-dossier-ink/50"

  const handleSignOut = async () => {
    await logout()
    if (authConfig?.auth_required) {
      router.push("/login")
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-mono tracking-wide ${roleColor}`}
      >
        {roleLabel}
      </span>
      <span className="text-[11px] font-mono text-dossier-ink/50 tracking-wide">{user.email}</span>
      {authConfig?.auth_required && (
        <button
          onClick={handleSignOut}
          className="text-[11px] font-mono text-dossier-ink/30 transition-colors hover:text-dossier-ink/70 tracking-wide"
        >
          SIGN·OUT
        </button>
      )}
    </div>
  )
}
