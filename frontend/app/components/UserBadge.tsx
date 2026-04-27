"use client"

import { usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"
import { useSession } from "../lib/SessionContext"

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  analyst: "Analyst",
  read_only: "Read-only",
}

const ROLE_COLORS: Record<string, string> = {
  admin: "border-indigo-700 text-indigo-400",
  analyst: "border-emerald-700 text-emerald-400",
  read_only: "border-zinc-600 text-zinc-400",
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
    return <span className="h-5 w-24 animate-pulse rounded bg-zinc-800" />
  }

  if (status === "anon" || !user) return null

  const roleLabel = ROLE_LABELS[user.role] ?? user.role
  const roleColor = ROLE_COLORS[user.role] ?? "border-zinc-600 text-zinc-400"

  const handleSignOut = async () => {
    await logout()
    if (authConfig?.auth_required) {
      router.push("/login")
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${roleColor}`}
      >
        {roleLabel}
      </span>
      <span className="text-xs text-zinc-400">{user.email}</span>
      {authConfig?.auth_required && (
        <button
          onClick={handleSignOut}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Sign out
        </button>
      )}
    </div>
  )
}
