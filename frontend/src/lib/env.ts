// The only module that reads import.meta.env. Throws at boot so a missing
// variable fails loudly instead of surfacing later as a confusing request error.

function readUrl(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required env var ${name} — set it in frontend/.env`)
  }
  if (!URL.canParse(value)) {
    throw new Error(`Env var ${name} is not a valid URL: ${value}`)
  }
  return value.replace(/\/+$/, "")
}

function readString(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required env var ${name} — set it in frontend/.env`)
  }
  return value
}

export const env = {
  apiBaseUrl: readUrl("VITE_API_BASE_URL", import.meta.env.VITE_API_BASE_URL),
  supabaseUrl: readUrl("VITE_SUPABASE_URL", import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: readString("VITE_SUPABASE_ANON_KEY", import.meta.env.VITE_SUPABASE_ANON_KEY),
} as const
