import { Button } from "@/components/ui/button";
import { useThreads } from "@/hooks/use-threads";

export function ChatsPage() {
  const { startNewChat, creating } = useThreads();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      <h1 className="text-xl font-semibold">Start a Conversion</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        Choose an existing thread from the sidebar or create a new chat to ask
        questions about SEC filings.
      </p>
      <Button onClick={startNewChat} disabled={creating}>
        New chat
      </Button>
    </div>
  );
}
