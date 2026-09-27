import { createClient } from "@supabase/supabase-js"

import { env } from "@/lib/env"

// Browser client: persists the session in localStorage and refreshes tokens
// automatically. Uses the public anon key only — never the service-role key.
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey)
