import { paraglideVitePlugin } from '@inlang/paraglide-js';
import Icons from 'unplugin-icons/vite'
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    sveltekit(),
    Icons({ compiler: 'svelte' }),

    paraglideVitePlugin({
      project: './project.inlang',
      outdir: './src/lib/paraglide',
      emitTsDeclarations: true
    })
  ],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8099'
      // ...
    },
    host: '127.0.0.1',
    port: 5173
  }
});
