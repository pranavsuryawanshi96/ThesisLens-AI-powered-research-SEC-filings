import { PlusIcon } from "lucide-react"
import { NavLink } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/hooks/use-auth"
import type { Thread } from "@/lib/chats"
import { cn } from "@/lib/utils"

type Props = {
  threads: Thread[] | null
  error: string | null
  creating: boolean
  onNewChat: () => void
}

export function ThreadSidebar({ threads, error, creating, onNewChat }: Props) {
  const { user, signOut } = useAuth()

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r bg-muted/30">
      <div className="p-3">
        <Button className="w-full" onClick={onNewChat} disabled={creating}>
          <PlusIcon />
          {creating ? "Creating…" : "New chat"}
        </Button>
      </div>

      <nav aria-label="Past conversations" className="flex-1 overflow-y-auto px-2">
        {error && <p className="px-2 pb-2 text-sm text-destructive">{error}</p>}
        {threads === null && !error && (
          <div className="grid gap-2 px-2">
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
          </div>
        )}
        {threads?.length === 0 && (
          <p className="px-2 text-sm text-muted-foreground">No conversations yet.</p>
        )}
        <ul className="grid gap-0.5">
          {threads?.map((thread) => (
            <li key={thread.id}>
              <NavLink
                to={`/chats/${thread.id}`}
                className={({ isActive }) =>
                  cn(
                    "block truncate rounded-md px-2 py-1.5 text-sm hover:bg-muted",
                    isActive && "bg-muted font-medium",
                  )
                }
              >
                {thread.title ?? "New chat"}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex items-center gap-2 border-t p-3">
        <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
          {user?.email}
        </span>
        <Button variant="ghost" size="sm" onClick={signOut}>
          Sign out
        </Button>
      </div>
    </aside>
  )
}
