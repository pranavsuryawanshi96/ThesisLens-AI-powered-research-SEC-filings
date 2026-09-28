import { DefaultChatTransport } from "ai"

import { getAccessToken } from "@/lib/api"
import { env } from "@/lib/env"

// The stream can't go through the `api` client (it buffers the whole body), so the
// AI SDK transport does the fetch and we supply the same bearer token.
export const chatTransport = new DefaultChatTransport({
  api: `${env.apiBaseUrl}/chat/stream`,
  headers: async (): Promise<Record<string, string>> => {
    const token = await getAccessToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  },
  // The chat id is the thread id. Only the new user message is sent: the backend
  // treats stored history as the source of truth.
  prepareSendMessagesRequest: ({ id, messages }) => ({
    body: { threadId: id, messages: messages.slice(-1) },
  }),
})
