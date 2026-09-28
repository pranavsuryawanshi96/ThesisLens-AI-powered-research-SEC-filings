import { useCallback, useEffect, useMemo, useState } from "react"
import { Outlet, useNavigate } from "react-router-dom"

import { ThreadSidebar } from "@/components/chat/thread-sidebar"
import type { ThreadsContext } from "@/hooks/use-threads"
import { createThread, listThreads, type Thread } from "@/lib/chats"
import { describeError } from "@/lib/errors"

export function ChatLayout() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await listThreads())
      setError(null)
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  const startNewChat = useCallback(async () => {
    setCreating(true)
    try {
      const thread = await createThread()
      setThreads((current) => [thread, ...(current ?? [])])
      navigate(`/chats/${thread.id}`)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setCreating(false)
    }
  }, [navigate])

  useEffect(() => {
    listThreads()
      .then(setThreads)
      .catch((err: unknown) => setError(describeError(err)))
  }, [])

  const context = useMemo<ThreadsContext>(
    () => ({ refreshThreads, startNewChat, creating }),
    [refreshThreads, startNewChat, creating],
  )

  return (
    <div className="flex h-svh">
      <ThreadSidebar
        threads={threads}
        error={error}
        creating={creating}
        onNewChat={startNewChat}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <Outlet context={context} />
      </main>
    </div>
  )
}
