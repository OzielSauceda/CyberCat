"use client"

import { useRouter } from "next/navigation"
import { useEffect, useState, type FormEvent } from "react"
import { login } from "../lib/auth"
import { useSession } from "../lib/SessionContext"

export default function LoginPage() {
  const router = useRouter()
  const { status, authConfig, refresh } = useSession()

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Redirect away if auth is not required or user is already authed
  useEffect(() => {
    if (authConfig !== null && !authConfig.auth_required) {
      router.replace("/")
      return
    }
    if (status === "authed") {
      const params = new URLSearchParams(
        typeof window !== "undefined" ? window.location.search : ""
      )
      router.replace(params.get("next") ?? "/")
    }
  }, [status, authConfig, router])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      await refresh()
      const params = new URLSearchParams(window.location.search)
      router.push(params.get("next") ?? "/")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed")
    } finally {
      setSubmitting(false)
    }
  }

  if (authConfig === null || status === "loading") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <span className="animate-pulse text-zinc-500 text-sm">Loading…</span>
      </div>
    )
  }

  if (!authConfig.auth_required || status === "authed") {
    return null
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-sm space-y-6 rounded-xl border border-zinc-800 bg-zinc-900 p-8">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">
            <span className="font-bold text-indigo-400">[CC]</span> CyberCat
          </h1>
          <p className="mt-1 text-sm text-zinc-400">Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="mb-1 block text-xs font-medium text-zinc-400"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="operator@example.com"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-xs font-medium text-zinc-400"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="••••••••"
            />
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>

          {authConfig.oidc_enabled && (
            <a
              href="/v1/auth/oidc/login"
              className="block w-full rounded-lg border border-zinc-600 px-4 py-2 text-center text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800"
            >
              Sign in with SSO
            </a>
          )}
        </form>
      </div>
    </div>
  )
}
