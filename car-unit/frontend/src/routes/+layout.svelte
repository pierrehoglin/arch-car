<script lang="ts">
  import { page } from '$app/state'
  import type { Snippet } from 'svelte'
  import Header from '$lib/Header.svelte'
  import Rail from '$lib/Rail.svelte'
  import { accent, display, themeAttr } from '$lib/settings.svelte'
  import '../app.css'

  interface Props {
    children: Snippet
  }

  let { children }: Props = $props()

  const titles: Record<string, string> = {
    '/': 'Home',
    '/media': 'Media',
    '/map': 'Map',
    '/phone': 'Phone',
    '/car': 'Car',
    '/camera': 'Camera',
    '/settings': 'Settings',
  }

  const path = $derived(page.url.pathname)

  const title = $derived(
    titles[path] ??
      Object.entries(titles)
        .filter(([href]) => href !== '/' && path.startsWith(href))
        .map(([, name]) => name)[0] ??
      'Home',
  )

  /* Theme goes on the document element rather than a wrapper, so the
     page background matches during overscroll. The accent is set
     inline because it is resolved per theme rather than declared in
     the stylesheet. */
  $effect(() => {
    const root = document.documentElement
    root.dataset.theme = themeAttr()
    root.style.setProperty('--accent', accent())
  })
</script>

<svelte:head><title>{title} — Saab 9-5</title></svelte:head>

<div class="shell">
  <Rail {path} />

  <div class="main">
    <Header
      {title}
      volume={display.volume}
      onvolume={(v) => (display.volume = v)}
    />

    <main class="content">
      {@render children()}
    </main>
  </div>
</div>

<style>
  .shell {
    display: grid;
    grid-template-columns: 120px 1fr;
    height: 100%;
    background: var(--bg);
  }

  .main {
    display: grid;
    grid-template-rows: 64px 1fr;
    min-width: 0;
  }

  .content {
    min-height: 0;
    overflow: hidden;
  }
</style>
