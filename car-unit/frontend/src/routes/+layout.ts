/* A kiosk SPA: every screen reads live device state, so there is
   nothing worth rendering on a server, and prerendering would only
   produce pages that are stale the moment they are served. */
export const ssr = false
export const prerender = false
