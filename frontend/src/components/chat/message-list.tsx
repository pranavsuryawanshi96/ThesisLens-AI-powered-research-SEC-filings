import type { ChatStatus, UIMessage } from "ai"
import { useEffect, useRef } from "react"

import { MessageItem } from "@/components/chat/message-item"
import { StreamingIndicator } from "@/components/chat/streaming-indicator"

type Props = {
  messages: UIMessage[]
  status: ChatStatus
}

export function MessageList({ messages, status }: Props) {
  const endRef = useRef<HTMLDivElement>(null)

  // Runs on every streamed delta too, keeping the newest text in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" })
  }, [messages, status])

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto grid w-full max-w-3xl gap-4 px-4 py-6">
        {messages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground">
            Ask a question to get started.
          </p>
        )}
        {messages.map((message) => (
          <MessageItem key={message.id} message={message} />
        ))}
        {status === "submitted" && <StreamingIndicator />}
        <div ref={endRef} />
      </div>
    </div>
  )
}
