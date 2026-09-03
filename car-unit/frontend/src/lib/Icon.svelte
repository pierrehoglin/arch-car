<script lang="ts">
  /* Tabler, through unplugin-icons.

     A 24px grid with a 2px stroke throughout, which is why it suits
     this panel: Material mixes filled and outlined shapes, and beside
     a stroked set the filled ones read a weight heavier than
     everything around them.

     Outlined throughout, except the transport row -- see below.

     Resolved at build time and tree-shaken, so only what is imported
     here reaches the bundle, and nothing is fetched at runtime --
     which matters for a unit that spends time out of signal.

     Kept behind a name prop rather than importing at each call site:
     the mapping from what a thing is to which glyph shows it lives in
     one place, and swapping a glyph does not mean touching screens. */

  import type { Component } from 'svelte'

  import IconCamera from '~icons/tabler/camera'
  import IconCar from '~icons/tabler/brand-speedtest'
  import IconCloud from '~icons/tabler/cloud'
  import IconCompass from '~icons/tabler/compass'
  import IconHeading from '~icons/tabler/navigation'
  import IconHome from '~icons/tabler/home'
  import IconLocate from '~icons/tabler/current-location'
  import IconMap from '~icons/tabler/map'
  import IconMinus from '~icons/tabler/minus'
  import IconMusic from '~icons/tabler/music'
  import IconPhone from '~icons/tabler/phone'
  import IconPlus from '~icons/tabler/plus'
  import IconPower from '~icons/tabler/power'
  import IconSearch from '~icons/tabler/search'
  import IconSettings from '~icons/tabler/settings'
  import IconVolume from '~icons/tabler/volume'
  import IconVolumeOff from '~icons/tabler/volume-off'

  /* The transport row is the exception to the outlined set. These
     sit on filled circles at 22-30px, where a 2px outline reads as a
     hollow shape rather than a button face -- and the three read as
     one group only if they share a weight. Every other glyph here is
     the stroked variant. */
  import IconNext from '~icons/tabler/player-skip-forward-filled'
  import IconPause from '~icons/tabler/player-pause-filled'
  import IconPlay from '~icons/tabler/player-play-filled'
  import IconPrevious from '~icons/tabler/player-skip-back-filled'

  interface Props {
    name: string
    size?: number
  }

  let { name, size = 24 }: Props = $props()

  const icons: Record<string, Component> = {
    add: IconPlus,
    camera: IconCamera,
    car: IconCar,
    cloud: IconCloud,
    compass: IconCompass,
    crosshair: IconLocate,
    heading: IconHeading,
    home: IconHome,
    map: IconMap,
    media: IconMusic,
    next: IconNext,
    note: IconMusic,
    pause: IconPause,
    phone: IconPhone,
    play: IconPlay,
    power: IconPower,
    previous: IconPrevious,
    remove: IconMinus,
    search: IconSearch,
    settings: IconSettings,
    volume: IconVolume,
    muted: IconVolumeOff,
  }

  const Glyph = $derived(icons[name])
</script>

{#if Glyph}
  <Glyph width={size} height={size} aria-hidden="true" />
{/if}
