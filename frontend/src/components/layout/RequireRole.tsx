import { Navigate, Outlet } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import type { UserRole } from "@/lib/api/types"

export function RequireRole({ minimumRole }: { minimumRole: UserRole }) {
  const { hasRole } = useAuth()

  if (!hasRole(minimumRole)) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
