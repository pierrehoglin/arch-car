/* A kiosk SPA: every screen reads live device state, so there is
   nothing worth rendering on a server, and prerendering would only
   produce pages that are stale the moment they are served. */
export const ssr = false
export const prerender = false

/* Mirage stands in for the daemon while the screens are being built.
   Guarded on DEV so it is stripped from the production bundle
   entirely -- a mock server shipped to the car would silently answer
   every request the daemon should have. */
if (import.meta.env.DEV) {
  const { makeServer } = await import('$lib/mirage/server')
  makeServer()
}
