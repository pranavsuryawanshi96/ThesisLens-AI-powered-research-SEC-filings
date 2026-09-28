import { APICallError } from "ai"

import { ApiError } from "@/lib/api"
import { errorMessage } from "@/lib/http"

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError"
}

export function errorStatus(error: unknown): number | null {
  if (error instanceof ApiError) return error.status
  if (APICallError.isInstance(error)) return error.statusCode ?? null
  return null
}

// Covers both our `api` client errors and the AI SDK's errors from /chat/stream.
export function describeError(error: unknown): string {
  if (error instanceof ApiError && error.isNetworkError) {
    return "Can't reach the backend. Is it running, and does ALLOWED_ORIGINS include this site?"
  }
  if (error instanceof ApiError && error.isTimeout) return "The backend took too long to respond."
  if (errorStatus(error) === 401) return "Your session has expired. Sign in again."
  if (error instanceof ApiError) return error.message
  if (APICallError.isInstance(error)) return streamErrorMessage(error)
  // fetch's bare TypeError: the transport doesn't wrap network/CORS failures.
  if (error instanceof TypeError) return "Can't reach the backend. Check your connection."
  return error instanceof Error ? error.message : "Unexpected error"
}

function streamErrorMessage(error: APICallError): string {
  const status = error.statusCode ?? 0
  try {
    return errorMessage(JSON.parse(error.responseBody ?? ""), status)
  } catch {
    return status ? `Request failed with status ${status}` : error.message
  }
}
