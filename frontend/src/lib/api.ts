import { env } from "@/lib/env"
import { createHttpClient } from "@/lib/http"
import { supabase } from "@/lib/supabase"

export { ApiError } from "@/lib/http"

export async function getAccessToken(): Promise<string | null> {
  // getSession() refreshes an expired access token before returning it.
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
  
}

// Every backend call goes through this: base URL, JSON, timeouts and the
// signed-in user's bearer token are handled here, never in components.
export const api = createHttpClient({
  baseUrl: env.apiBaseUrl,
  getToken: getAccessToken,
})
