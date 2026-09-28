import type { FormEvent, KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

type Props = {
  busy: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export function ChatInput({ busy, onSend, onStop }: Props) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const text = String(new FormData(form).get("message")).trim()
    if (!text || busy) return
    onSend(text)
    form.reset()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter inserts a newline; skip while an IME is composing.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-auto flex w-full max-w-3xl items-end gap-2 px-4 pb-4"
    >
      <Textarea
        name="message"
        aria-label="Message"
        placeholder="Ask about a filing…"
        rows={1}
        autoFocus
        className="max-h-48 min-h-10 resize-none"
        onKeyDown={handleKeyDown}
      />
      {busy ? (
        <Button type="button" variant="outline" size="lg" onClick={onStop}>
          Stop
        </Button>
      ) : (
        <Button type="submit" size="lg">
          Send
        </Button>
      )}
    </form>
  )
}
