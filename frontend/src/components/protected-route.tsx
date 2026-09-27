import { Navigate, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"

export function ProtectedRoute() {
  const { session, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <p className="p-8 text-sm text-muted-foreground">Loading…</p>
  }
  if (!session) {
    // Remember where they were going so login can send them back there.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
