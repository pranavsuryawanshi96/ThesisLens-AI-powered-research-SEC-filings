import type { UIMessage } from "ai"

import { api } from "@/lib/api"

export type Thread = {
  id: string
  title: string | null
  createdAt: string
  updatedAt: string
}

export function listThreads(): Promise<Thread[]> {
  return api.get<Thread[]>("/chat/threads")
}

export function createThread(): Promise<Thread> {
  return api.post<Thread>("/chat/threads")
}

// Stored messages are AI SDK UIMessages, so they seed useChat as-is.
export function listMessages(threadId: string, signal?: AbortSignal): Promise<UIMessage[]> {
  return api.get<UIMessage[]>(`/chat/threads/${threadId}/messages`, { signal })
}
