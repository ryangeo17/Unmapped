const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const TIMEOUT_MS = 20_000

export class ApiError extends Error {
  status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface ApiFetchOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal // e.g. from TanStack Query, to cancel stale requests
}

// The only place in the app that calls fetch. Returns parsed JSON as
// `unknown`; callers pass it through an adapter to get a domain type.
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<unknown> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort('timeout'), TIMEOUT_MS)
  options.signal?.addEventListener('abort', () => controller.abort(options.signal?.reason))

  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers: options.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    })
  } catch (err) {
    if (controller.signal.reason === 'timeout') {
      throw new ApiError('The server took too long to respond.')
    }
    if (controller.signal.aborted) throw err // cancelled by the caller; not a user-facing error
    throw new ApiError("Couldn't reach the server. Check your connection.")
  } finally {
    clearTimeout(timeout)
  }

  const data: unknown = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(errorMessage(data) ?? `Request failed (${res.status}).`, res.status)
  }
  return data
}

// Pull a readable message out of common JSON error shapes
// ({ message }, { error }, FastAPI's { detail }).
function errorMessage(data: unknown): string | undefined {
  if (typeof data !== 'object' || data === null) return undefined
  const d = data as Record<string, unknown>
  for (const key of ['message', 'error', 'detail']) {
    if (typeof d[key] === 'string') return d[key]
  }
  return undefined
}
