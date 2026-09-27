import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/hooks/use-auth"
import { api, ApiError } from "@/lib/api"

type Me = { id: string; email: string | null }

function describe(error: unknown): string {
  if (!(error instanceof ApiError)) return "Unexpected error"
  if (error.isNetworkError) {
    return "Can't reach the backend. Is it running, and does ALLOWED_ORIGINS include this site?"
  }
  if (error.isTimeout) return "The backend took too long to respond."
  return `${error.status}: ${error.message}`
}

// Placeholder home screen until the chat UI lands in Phase 3. Calling /me proves the
// Supabase token reaches the backend and is accepted.
export function HomePage() {
  const { user, signOut } = useAuth()
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api
      .get<Me>("/me", { signal: controller.signal })
      .then(setMe)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return
        setError(describe(err))
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="mx-auto grid max-w-xl gap-4 p-8">
      <h1 className="text-2xl font-semibold">ThesisLens</h1>
      <p className="text-sm text-muted-foreground">Signed in as {user?.email}</p>
      <section className="rounded-lg border p-4 text-sm">
        <h2 className="mb-2 font-medium">Backend check (GET /me)</h2>
        {me && <p>OK — backend sees user {me.email}</p>}
        {error && <p className="text-destructive">{error}</p>}
        {!me && !error && <p className="text-muted-foreground">Checking…</p>}
      </section>
      <Button variant="outline" className="w-fit" onClick={signOut}>
        Sign out
      </Button>
    </main>
  )
}
