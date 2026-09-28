import type { UIMessage } from "ai"

type Props = {
  message: UIMessage
}

// Text parts only for now; citation parts get their own rendering in Phase 7.
export function MessageItem({ message }: Props) {
  const text = message.parts
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")

  if (message.role === "user") {
    return (
      <div className="max-w-[80%] justify-self-end rounded-2xl bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
        {text}
      </div>
    )
  }
  return <div className="text-sm leading-relaxed whitespace-pre-wrap">{text}</div>
}
