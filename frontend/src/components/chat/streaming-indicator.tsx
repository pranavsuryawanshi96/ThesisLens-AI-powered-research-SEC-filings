const DOT_DELAYS = ["[animation-delay:0ms]", "[animation-delay:150ms]", "[animation-delay:300ms]"]

// Shown between sending and the first streamed token.
export function StreamingIndicator() {
  return (
    <div role="status" aria-label="Assistant is responding" className="flex gap-1 py-2">
      {DOT_DELAYS.map((delay) => (
        <span
          key={delay}
          className={`size-2 animate-bounce rounded-full bg-muted-foreground/60 ${delay}`}
        />
      ))}
    </div>
  )
}
