import type { UIMessage } from "ai"
import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"

import { ChatThread } from "@/components/chat/chat-thread"
import { Skeleton } from "@/components/ui/skeleton"
import { listMessages } from "@/lib/chats"
import { describeError, errorStatus, isAbortError } from "@/lib/errors"

type History =
  | { threadId: string; messages: UIMessage[] }
  | { threadId: string; error: string }

function describeHistoryError(error: unknown): string {
  const status = errorStatus(error)
  // 403 (another user's thread), 404 and 422 (malformed id) all mean the same to the user.
  if (status === 403 || status === 404 || status === 422) {
    return "This conversation doesn't exist or isn't yours."
  }
  return describeError(error)
}

export function ThreadPage() {
  const { threadId } = useParams<"threadId">()
  const [history, setHistory] = useState<History | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    listMessages(threadId!, controller.signal)
      .then((messages) => setHistory({ threadId: threadId!, messages }))
      .catch((err: unknown) => {
        if (isAbortError(err)) return
        setHistory({ threadId: threadId!, error: describeHistoryError(err) })
      })
    return () => controller.abort()
  }, [threadId])

  // Tagging the result with its thread means switching threads shows the skeleton
  // until the new history arrives, without resetting state inside the effect.
  if (!history || history.threadId !== threadId) {
    return (
      <div className="mx-auto grid w-full max-w-3xl gap-4 px-4 py-6">
        <Skeleton className="h-10 w-2/3 justify-self-end" />
        <Skeleton className="h-20" />
      </div>
    )
  }

  if ("error" in history) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
        <p className="text-sm text-destructive">{history.error}</p>
        <Link to="/chats" className="text-sm underline underline-offset-4">
          Back to chats
        </Link>
      </div>
    )
  }

  // `key` gives each thread a fresh useChat instance seeded with its own history.
  return <ChatThread key={threadId} threadId={threadId!} initialMessages={history.messages} />
}
