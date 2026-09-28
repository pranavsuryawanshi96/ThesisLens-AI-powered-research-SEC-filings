import { useChat } from "@ai-sdk/react"
import type { UIMessage } from "ai"

import { ChatInput } from "@/components/chat/chat-input"
import { MessageList } from "@/components/chat/message-list"
import { Button } from "@/components/ui/button"
import { useThreads } from "@/hooks/use-threads"
import { chatTransport } from "@/lib/chat-transport"
import { describeError } from "@/lib/errors"

type Props = {
  threadId: string
  initialMessages: UIMessage[]
}

// Seeded with stored history; from then on the AI SDK owns the in-flight UI state.
export function ChatThread({ threadId, initialMessages }: Props) {
  const { refreshThreads } = useThreads()
  const { messages, sendMessage, status, error, stop, regenerate } = useChat({
    id: threadId,
    messages: initialMessages,
    transport: chatTransport,
    onFinish: ({ isAbort, isDisconnect, isError }) => {
      // A completed turn renames the thread and bumps it to the top of the sidebar.
      if (!isAbort && !isDisconnect && !isError) void refreshThreads()
    },
  })

  const busy = status === "submitted" || status === "streaming"

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <MessageList messages={messages} status={status} />
      {error && (
        <div
          role="alert"
          className="mx-auto mb-2 flex w-full max-w-3xl items-center gap-3 px-4 text-sm text-destructive"
        >
          <p className="flex-1">{describeError(error)}</p>
          <Button variant="outline" size="sm" onClick={() => regenerate()}>
            Retry
          </Button>
        </div>
      )}
      <ChatInput busy={busy} onSend={(text) => sendMessage({ text })} onStop={stop} />
    </div>
  )
}
