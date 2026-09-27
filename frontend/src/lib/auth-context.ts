import { createContext } from "react"
import type { Session, User } from "@supabase/supabase-js"

export type AuthState = {
  session: Session | null
  user: User | null
  // True until Supabase has restored (or ruled out) a saved session on page load.
  loading: boolean
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)
