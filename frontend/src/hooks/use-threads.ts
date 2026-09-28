import { useOutletContext } from "react-router-dom"

export type ThreadsContext = {
  refreshThreads: () => Promise<void>
  startNewChat: () => Promise<void>
  creating: boolean
}

// Provided by ChatLayout to every chat route through <Outlet context>.
export function useThreads(): ThreadsContext {
  return useOutletContext<ThreadsContext>()
}
