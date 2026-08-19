import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"
import { authApi } from "@/lib/api/endpoints/auth"
import { tokenStore } from "@/lib/api/tokenStore"
import type { LoginPayload, RegisterPayload } from "@/lib/api/endpoints/auth"
import type { TenantRead, UserRead, UserRole } from "@/lib/api/types"

const ROLE_RANK: Record<UserRole, number> = { viewer: 0, operator: 1, admin: 2 }

interface AuthContextValue {
  user: UserRead | null
  tenant: TenantRead | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (payload: LoginPayload) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  logout: () => void
  refetchMe: () => Promise<void>
  hasRole: (minimumRole: UserRole) => boolean
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = React.useState<UserRead | null>(null)
  const [tenant, setTenant] = React.useState<TenantRead | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  const loadMe = React.useCallback(async () => {
    if (!tokenStore.hasSession()) {
      setUser(null)
      setTenant(null)
      setIsLoading(false)
      return
    }
    try {
      const me = await authApi.me()
      setUser(me.user)
      setTenant(me.tenant)
    } catch {
      tokenStore.clear()
      setUser(null)
      setTenant(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadMe()
  }, [loadMe])

  React.useEffect(() => {
    return tokenStore.onUnauthorized(() => {
      setUser(null)
      setTenant(null)
      queryClient.clear()
    })
  }, [queryClient])

  const login = React.useCallback(
    async (payload: LoginPayload) => {
      const tokens = await authApi.login(payload)
      tokenStore.setTokens(tokens.access_token, tokens.refresh_token)
      await loadMe()
    },
    [loadMe]
  )

  const register = React.useCallback(
    async (payload: RegisterPayload) => {
      const tokens = await authApi.register(payload)
      tokenStore.setTokens(tokens.access_token, tokens.refresh_token)
      await loadMe()
    },
    [loadMe]
  )

  const logout = React.useCallback(() => {
    tokenStore.clear()
    setUser(null)
    setTenant(null)
    queryClient.clear()
  }, [queryClient])

  const hasRole = React.useCallback(
    (minimumRole: UserRole) => {
      if (!user) return false
      return ROLE_RANK[user.role] >= ROLE_RANK[minimumRole]
    },
    [user]
  )

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      tenant,
      isLoading,
      isAuthenticated: Boolean(user),
      login,
      register,
      logout,
      refetchMe: loadMe,
      hasRole,
    }),
    [user, tenant, isLoading, login, register, logout, loadMe, hasRole]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider")
  return ctx
}
