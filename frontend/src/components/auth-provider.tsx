import { useEffect, useMemo, useState, type ReactNode } from "react"
import type { Session } from "@supabase/supabase-js"

import { AuthContext } from "@/lib/auth-context"
import { supabase } from "@/lib/supabase"

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fires once immediately with the restored session (INITIAL_SESSION), then on
    // every sign-in, sign-out and token refresh — so no separate getSession() call.
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      setLoading(false)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const value = useMemo(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      signOut: async () => {
        await supabase.auth.signOut()
      },
    }),
    [session, loading],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
