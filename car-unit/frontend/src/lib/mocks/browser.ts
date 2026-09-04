import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)

/**
 * Start intercepting.
 *
 * `onUnhandledRequest: 'bypass'` so Vite's own traffic, the fonts and
 * the icons go to the network untouched -- only /api is mocked, and
 * warning about everything else would bury the one message that
 * matters.
 */
export const startMocking = () =>
  worker.start({
    onUnhandledRequest: 'bypass',
    quiet: false,
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
