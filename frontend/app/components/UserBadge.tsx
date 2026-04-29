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
    <div className="flex items-center gap-1.5">
      {/* Operator icon */}
      <svg
        width="11" height="11" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
        className="shrink-0 text-dossier-ink/25"
        aria-hidden
      >
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <path d="M8 21h8M12 17v4" />
        <path d="M7 10l3 3-3 3" />
        <line x1="13" y1="16" x2="17" y2="16" />
      </svg>

      {/* Role pill */}
      <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-mono tracking-widest ${roleColor}`}>
        {roleLabel}
      </span>

      {/* Email */}
      <span className="font-mono text-[13px] text-dossier-ink/55 tracking-wide max-w-[140px] truncate">
        {user.email}
      </span>

      {/* Sign out */}
      {authConfig?.auth_required && (
        <>
          <div className="h-3 w-px bg-dossier-paperEdge mx-0.5" />
          <button
            onClick={handleSignOut}
            className="font-mono text-xs uppercase tracking-widest text-dossier-ink/25 transition-colors hover:text-dossier-ink/60"
          >
            ⏻
          </button>
        </>
      )}
    </div>
  )
}
