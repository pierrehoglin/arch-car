<script lang="ts">
  /* The pin's marker, as an element for MapLibre to place -- the same
     arrangement as the car's: drawn here, moved into the map by
     MapLibre, still updated by Svelte wherever it has gone.

     A classic pin, its point on the spot: anchored at the bottom when
     it is made into a Marker. In the accent with a white rim, like the
     car, but a different shape, so the two are never mistaken for each
     other. */

  interface Props {
    element?: HTMLDivElement
  }

  let { element = $bindable() }: Props = $props()
</script>

<div hidden>
  <div bind:this={element} class="pin" role="img" aria-label="Pin">
    <svg viewBox="0 0 36 48" width="36" height="48" aria-hidden="true">
      <path
        class="body"
        d="M18 46 C18 46 4 28.5 4 18 A14 14 0 0 1 32 18 C32 28.5 18 46 18 46 Z"
      />
      <circle class="eye" cx="18" cy="18" r="5.5" />
    </svg>
  </div>
</div>

<style>
  /* Grabbable: it can be dragged to a better spot. */
  .pin {
    width: 36px;
    height: 48px;
    cursor: grab;
  }

  svg {
    display: block;
    overflow: visible;
  }

  .body {
    fill: var(--accent);
    stroke: #fff;
    stroke-width: 2.5;
    stroke-linejoin: round;
    filter: drop-shadow(0 2px 3px rgb(0 0 0 / 0.45));
  }

  .eye {
    fill: #fff;
  }
</style>
