import { setupWorker } from 'msw/browser'
import { http, passthrough } from 'msw'
import { handlers } from './handlers'
import { stream } from './stream'
import { groupOf } from './groups'

/* The worker runs with whichever handlers are switched on.
 *
 * Filtered rather than started and stopped: a handler list is the
 * natural unit here, and it means a group can be turned off while
 * the rest keep answering.
 */

/* Last, and always present. Two reasons: resetHandlers() with an
   empty list resets to the original set rather than clearing it,
   which would silently turn everything back on; and an explicit
   passthrough says what happens to an unmatched /api call rather
   than leaving it to a global option. */
const fallthrough = http.all('/api/*', () => passthrough())

export const worker = setupWorker(fallthrough)

/* The stream is matched by identity rather than by its path. An sse
   handler is not an http one and does not have to describe itself
   the same way, and a filter that quietly failed to place it would
   drop it from every set -- which looks exactly like the mock not
   working. */
function groupFor(handler: unknown): string {
  if (handler === stream) return 'events'

  const info = (handler as { info?: { path?: unknown } }).info
  return groupOf(String(info?.path ?? ''))
}

/** The handlers for a set of enabled groups. */
export function handlersFor(enabled: Record<string, boolean>) {
  const on = handlers.filter((handler) => enabled[groupFor(handler)])
  return [...on, fallthrough]
}

/**
 * Start intercepting.
 *
 * `onUnhandledRequest: 'bypass'` so Vite's own traffic, the fonts and
 * the icons go to the network untouched -- only /api is considered,
 * and warning about everything else would bury the one message that
 * matters.
 */
export const startMocking = (enabled: Record<string, boolean>) => {
  worker.resetHandlers(...handlersFor(enabled))
  return worker.start({
    onUnhandledRequest: 'bypass',
    quiet: false,
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}

/** Change which groups are mocked, without a restart. */
export const applyHandlers = (enabled: Record<string, boolean>) => {
  worker.resetHandlers(...handlersFor(enabled))
}
