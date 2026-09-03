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
      muted={display.muted}
      onmute={(v) => (display.muted = v)}
    />

    <main class="content">
      {@render children()}
    </main>
  </div>
</div>

<style>
  /* minmax(0, 1fr) throughout, not a bare 1fr.
     
     1fr means minmax(auto, 1fr), and auto as a minimum is min-content
     -- so a track can never shrink below what its content demands. A
     page with a long list then pushes the row taller than the screen
     instead of scrolling inside it, which is what went wrong on the
     phone screen.
     
     Stating the zero minimum fixes it without pinning anything to the
     panel's size, so the layout still holds in a browser window at
     some other dimension. */
  .shell {
    display: grid;
    grid-template-columns: 120px minmax(0, 1fr);
    /* The row has to be declared too. Without it the single implicit
       row is auto -- sized to content -- so .main could never shrink
       however many zero minimums were stated below it. */
    grid-template-rows: minmax(0, 1fr);
    /* dvh rather than a chain of height:100% from html down. One
       broken link anywhere in that chain silently turns every
       percentage into auto, and this is a kiosk filling the screen. */
    height: 100dvh;
    background: var(--bg);
  }

  .main {
    display: grid;
    grid-template-rows: 64px minmax(0, 1fr);
    min-width: 0;
  }

  .content {
    min-height: 0;
    overflow: hidden;
  }
</style>
