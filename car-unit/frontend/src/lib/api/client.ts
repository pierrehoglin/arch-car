/* The one place the frontend talks to the daemon.
 *
 * Everything is served under /api, which the Vite dev server proxies
 * to 127.0.0.1:8099 and the daemon serves directly in production --
 * so the same relative paths work in both, with no base URL that
 * differs by environment and no CORS.
 *
 * There is no mock branch here. In development Mirage intercepts
 * fetch, so this code does a real request to a real URL and reads
 * real status codes -- the same path that runs against the daemon.
 * A mock inside the client would be a second code path that only
 * development exercises, and the first time it drifted, a screen
 * would work here and fail on the unit.
 */

/** How the API reports a failure: carlib.core.errors mapped to
 *  status codes, with the message and sometimes a hint. */
export interface ApiError {
  error: string
  type: string
  hint?: string
}

export class RequestFailed extends Error {
  status: number
  hint: string

  constructor(status: number, message: string, hint = '') {
    super(message)
    this.name = 'RequestFailed'
    this.status = status
    this.hint = hint
  }
}

interface Options {
  method?: string
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
  /** Scanning the band takes seconds, not milliseconds. */
  timeout?: number
}

const DEFAULT_TIMEOUT = 10_000

export async function request<T>(
  path: string,
  { method = 'GET', body, query, timeout = DEFAULT_TIMEOUT }: Options = {},
): Promise<T> {
  const url = new URL(`/api${path}`, location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value))
  }

  /* A timeout rather than waiting indefinitely: the daemon holds a
     USB device and a network link, either of which can hang, and a
     request that never settles leaves a screen spinning with nothing
     to say. */
  const abort = new AbortController()
  const timer = setTimeout(() => abort.abort(), timeout)

  let response: Response
  try {
    response = await fetch(url, {
      method,
      signal: abort.signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (cause) {
    const message =
      cause instanceof DOMException && cause.name === 'AbortError'
        ? 'the daemon did not answer in time'
        : 'cannot reach the daemon'
    throw new RequestFailed(0, message, 'systemctl --user status carlib')
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    let detail: ApiError | null = null
    try {
      detail = (await response.json()) as ApiError
    } catch {
      // A proxy error page rather than the daemon's own JSON.
    }
    throw new RequestFailed(
      response.status,
      detail?.error ?? `request failed (${response.status})`,
      detail?.hint ?? '',
    )
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
