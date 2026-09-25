<script lang="ts">
  import { page } from '$app/state'
  import type { Snippet } from 'svelte'
  import Header from '$lib/Header.svelte'
  import Rail from '$lib/Rail.svelte'
  import { connect, disconnect } from '$lib/api/stream.svelte'
  import { adjust, audio, setMuted, setVolume, watch } from '$lib/audio.svelte'
  import { watch as watchBluetooth } from '$lib/bluetooth.svelte'
  import { watch as watchNetwork } from '$lib/network.svelte'
  import PairingDialog from '$lib/ui/PairingDialog.svelte'
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

  /* One connection for the session, opened here rather than by a
     screen. The header shows volume everywhere, the source
     supervisor can interrupt at any moment, and a screen that owned
     the connection would close it on the way out -- so whatever was
     pushed while you were elsewhere would simply be missed.
     
     Screens subscribe to what they care about and unsubscribe when
     they go; the socket underneath outlives them. */
  $effect(() => {
    connect()
    return disconnect
  })

  /* Subscribed here rather than in the header, because the volume is
     shown on every screen and the header is never unmounted -- so
     the subscription has the same lifetime either way, and this
     keeps the component to displaying what it is given. */
  $effect(() => watch())

  /* Bluetooth is followed here, not on the settings screen: a phone
     can start pairing at any moment, and whoever is driving will not
     be looking at Connectivity when it does. */
  $effect(() => watchBluetooth())

  /* The header shows the radio on every screen, so it is followed
     here rather than by the settings page that changes it. */
  $effect(() => watchNetwork())

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
      volume={audio.percent}
      onvolume={setVolume}
      onstep={adjust}
      muted={audio.muted}
      onmute={setMuted}
    />

    <main class="content">
      {@render children()}
    </main>
  </div>
</div>

<!-- Over everything, because the phone is waiting and BlueZ gives up
     after half a minute. -->
<PairingDialog />

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
