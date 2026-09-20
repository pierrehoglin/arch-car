/* A kiosk SPA: every screen reads live device state, so there is
   nothing worth rendering on a server, and prerendering would only
   produce pages that are stale the moment they are served. */
export const ssr = false
export const prerender = false

/* MSW stands in for the daemon while the screens are being built,
   unless it has been switched off in Settings. Awaited, so the worker
   is intercepting before any screen makes its first request.

   Guarded on DEV, so neither the control nor msw itself reaches the
   production bundle -- a mock server shipped to the car would
   silently answer every request the daemon should have. */
if (import.meta.env.DEV) {
  const { init } = await import('$lib/mocks/control.svelte')
  await init()
}
