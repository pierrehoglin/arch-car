import adapter from '@sveltejs/adapter-static'
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

/* A plain SPA build the carlib daemon can serve as static files.
   No SSR: every screen reads live device state, so there is nothing
   useful to render on a server, and adapter-node would mean a second
   process running beside carlibd for no benefit.

   fallback: 'index.html' makes client-side routing work when the
   daemon serves a deep link like /settings directly. */

/** @type {import('@sveltejs/kit').Config} */
export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html',
      precompress: false,
    }),
  },
}
