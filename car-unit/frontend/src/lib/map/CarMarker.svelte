<script lang="ts">
  import type { CarLook } from './car'

  /* The car's marker, as an element for MapLibre to place.

     Rendered here so its look stays in a stylesheet rather than
     strings in TypeScript. It lives inside the hidden holder only
     until the map takes it: MapLibre moves the element into its own
     layer and positions it from then on, and Svelte still updates it
     wherever it has gone. */

  interface Props {
    element?: HTMLDivElement
    look: CarLook
    /** Pixels across. The home tile's map is small, and the car on it
     *  can be too. */
    size?: number
  }

  let { element = $bindable(), look, size = 48 }: Props = $props()
</script>

<div hidden>
  <div
    bind:this={element}
    class="car"
    class:stale={look.source !== 'gps'}
    style:width="{size}px"
    style:height="{size}px"
    role="img"
    aria-label={look.source === 'gps'
      ? 'Your car'
      : look.source === 'pin'
        ? 'Your car, at its pinned position'
        : 'Your car, where it last had a GPS fix'}
  >
    <!-- An arrow once the car has moved and there is a direction to
         show; a dot until then. -->
    <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden="true">
      <circle class="halo" cx="20" cy="20" r="19" />
      {#if look.pointing}
        <path class="body" d="M20 6 L30 31 L20 25.5 L10 31 Z" />
      {:else}
        <circle class="body" cx="20" cy="20" r="8.5" />
      {/if}
    </svg>
  </div>
</div>

<style>
  /* A white rim and a soft halo so it reads on the Day and Night maps
     alike, and over roads drawn in a similar colour. White in both: a
     rim in the theme's ink would vanish into the Night map, which is
     dark exactly where the car is. */
  .car {
    pointer-events: none;
  }

  svg {
    display: block;
    overflow: visible;
  }

  .halo {
    fill: color-mix(in srgb, var(--accent) 28%, transparent);
  }

  .body {
    fill: var(--accent);
    stroke: #fff;
    stroke-width: 2.5;
    stroke-linejoin: round;
    filter: drop-shadow(0 1px 2px rgb(0 0 0 / 0.45));
  }

  /* Anything but a live fix -- where the car last had one, or a
     pinned position: where the car was or is said to be, not where
     the GPS sees it. Grey, so it does not pass for live at a glance. */
  .stale .halo {
    fill: color-mix(in srgb, var(--text-faint) 20%, transparent);
  }

  .stale .body {
    fill: var(--text-faint);
  }
</style>
