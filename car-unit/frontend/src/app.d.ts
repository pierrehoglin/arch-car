/// <reference types="@sveltejs/kit" />
/// <reference types="unplugin-icons/types/svelte" />
// What types an image import. SvelteKit's generated tsconfig usually
// pulls this in already; naming it here means a png or jpg import is
// typed whether or not it does.
/// <reference types="vite/client" />

declare global {
  namespace App {}
}

export {}
