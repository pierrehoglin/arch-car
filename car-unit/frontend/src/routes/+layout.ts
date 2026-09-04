/* A kiosk SPA: every screen reads live device state, so there is
   nothing worth rendering on a server, and prerendering would only
   produce pages that are stale the moment they are served. */
export const ssr = false
export const prerender = false

/* MSW stands in for the daemon while the screens are being built. It
   intercepts through a Service Worker, so the app does real fetches
   to real URLs and reads real status codes -- and mocked responses
   appear in the Network tab.

   Guarded on DEV and awaited, so the worker is intercepting before
   any screen makes its first request, and so none of it reaches the
   production bundle. A mock server shipped to the car would silently
   answer every request the daemon should have. */
if (import.meta.env.DEV) {
  const { startMocking } = await import('$lib/mocks/browser')
  await startMocking()
}
