// Thin fetch wrapper: JSON in/out, bearer token, timeouts, typed errors.
// Knows nothing about Supabase or our API — see api.ts for the configured client.

export class ApiError extends Error {
  readonly status: number | null
  readonly isNetworkError: boolean
  readonly isTimeout: boolean
  readonly body: unknown

  constructor(
    message: string,
    options: {
      status: number | null
      isNetworkError?: boolean
      isTimeout?: boolean
      body?: unknown
      cause?: unknown
    },
  ) {
    super(message, { cause: options.cause })
    this.name = "ApiError"
    this.status = options.status
    this.isNetworkError = options.isNetworkError ?? false
    this.isTimeout = options.isTimeout ?? false
    this.body = options.body
  }
}

export type RequestOptions = {
  headers?: HeadersInit
  signal?: AbortSignal
  timeoutMs?: number
}

type HttpClientConfig = {
  baseUrl: string
  getToken?: () => Promise<string | null>
  timeoutMs?: number
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"

const DEFAULT_TIMEOUT_MS = 30_000

export function createHttpClient(config: HttpClientConfig) {
  async function request<T>(
    method: Method,
    path: string,
    body: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    const headers = new Headers(options.headers)
    headers.set("Accept", "application/json")
    if (body !== undefined) headers.set("Content-Type", "application/json")

    const token = await config.getToken?.()
    if (token) headers.set("Authorization", `Bearer ${token}`)

    const timeout = AbortSignal.timeout(
      options.timeoutMs ?? config.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    )
    const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout

    let response: Response
    try {
      response = await fetch(`${config.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ApiError("The server took too long to respond", {
          status: null,
          isTimeout: true,
          cause: error,
        })
      }
      // Caller cancelled on purpose (e.g. component unmounted) — not an API failure.
      if (error instanceof DOMException && error.name === "AbortError") throw error
      // fetch rejects with a bare TypeError for both network failures and CORS
      // blocks; the browser deliberately hides which one it was.
      throw new ApiError("Could not reach the server (network or CORS error)", {
        status: null,
        isNetworkError: true,
        cause: error,
      })
    }

    const data = await parseBody(response)
    if (!response.ok) {
      throw new ApiError(errorMessage(data, response.status), {
        status: response.status,
        body: data,
      })
    }
    return data as T
  }

  return {
    get: <T>(path: string, options?: RequestOptions) =>
      request<T>("GET", path, undefined, options),
    post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
      request<T>("POST", path, body, options),
    put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
      request<T>("PUT", path, body, options),
    patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
      request<T>("PATCH", path, body, options),
    delete: <T>(path: string, options?: RequestOptions) =>
      request<T>("DELETE", path, undefined, options),
  }
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return undefined
  const isJson = response.headers.get("Content-Type")?.includes("application/json")
  return isJson ? JSON.parse(text) : text
}

// FastAPI errors are {"detail": "..."}, or {"detail": [{msg, ...}]} for 422s.
export function errorMessage(data: unknown, status: number): string {
  if (typeof data === "object" && data !== null && "detail" in data) {
    const { detail } = data
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item: unknown) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String(item.msg)
            : String(item),
        )
        .join("; ")
    }
  }
  return `Request failed with status ${status}`
}
