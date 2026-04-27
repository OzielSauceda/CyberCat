"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import {
  type AuthConfig,
  type User,
  getAuthConfig,
  getMe,
  logout as apiLogout,
} from "./auth"

interface SessionState {
  user: User | null
  status: "loading" | "authed" | "anon"
  authConfig: AuthConfig | null
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const SessionContext = createContext<SessionState>({
  user: null,
  status: "loading",
  authConfig: null,
  refresh: async () => {},
  logout: async () => {},
})

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<"loading" | "authed" | "anon">("loading")
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)

  const fetchSession = useCallback(async () => {
    const [meResult, configResult] = await Promise.allSettled([
      getMe(),
      getAuthConfig(),
    ])

    if (configResult.status === "fulfilled") {
      setAuthConfig(configResult.value)
    }

    if (meResult.status === "fulfilled") {
      setUser(meResult.value)
      setStatus("authed")
    } else {
      setUser(null)
      setStatus("anon")
    }
  }, [])

  useEffect(() => {
    fetchSession()
  }, [fetchSession])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(null)
    setStatus("anon")
  }, [])

  return (
    <SessionContext.Provider
      value={{ user, status, authConfig, refresh: fetchSession, logout }}
    >
      {children}
    </SessionContext.Provider>
  )
}

export function useSession(): SessionState {
  return useContext(SessionContext)
}

export function useCanMutate(): boolean {
  const { user } = useSession()
  return user?.role === "analyst" || user?.role === "admin"
}
