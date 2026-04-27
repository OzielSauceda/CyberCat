const BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "")

export type UserRole = "admin" | "analyst" | "read_only"

export interface User {
  id: string | null
  email: string
  role: UserRole
  is_active: boolean
  created_at: string | null
}

export interface AuthConfig {
  auth_required: boolean
  oidc_enabled: boolean
}

export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${BASE}/v1/auth/config`, { cache: "no-store" })
  if (!res.ok) throw new Error(`auth/config ${res.status}`)
  return res.json() as Promise<AuthConfig>
}

export async function getMe(): Promise<User> {
  const res = await fetch(`${BASE}/v1/auth/me`, {
    credentials: "include",
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`auth/me ${res.status}`)
  return res.json() as Promise<User>
}

export async function login(email: string, password: string): Promise<User> {
  const res = await fetch(`${BASE}/v1/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? "Invalid credentials")
  }
  return res.json() as Promise<User>
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
  })
}
