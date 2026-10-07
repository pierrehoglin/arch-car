<script lang="ts">
  /* A Swedish speed limit sign: a white disc, a red ring, the limit in
     black. A dash when the limit is not known, so the sign does not
     come and go along roads that lack the tag.

     The same in Day and Night: it is a road sign, and is read as one.
     A short pulse when the limit changes -- keyed on `changes`, which
     counts them, so the same number twice in a row is not a change. */

  interface Props {
    limit: number | null
    /** Diameter, in pixels. */
    size?: number
    /** Changes counted so far; a new value pulses the sign. */
    changes?: number
  }

  let { limit, size = 56, changes = 0 }: Props = $props()

  const label = $derived(
    limit === null ? 'Speed limit not known' : `Speed limit ${limit}`,
  )
</script>

{#key changes}
  <div
    class="sign"
    class:pulse={changes > 0}
    style:--size="{size}px"
    role="img"
    aria-label={label}
  >
    {#if limit === null}
      <!-- A bar rather than a dash character, which at this size is a
           speck: as wide as two digits, so it reads as "no number". -->
      <span class="dash"></span>
    {:else}
      <span class="number" class:long={limit >= 100}>{limit}</span>
    {/if}
  </div>
{/key}

<style>
  .sign {
    display: grid;
    place-items: center;
    width: var(--size);
    height: var(--size);
    box-sizing: border-box;
    background: #fff;
    /* The ring at the sign's own proportion, about an eighth of it. */
    border: calc(var(--size) * 0.12) solid #d4231e;
    border-radius: 50%;
    box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
  }

  .number {
    font-family: var(--font-display);
    font-size: calc(var(--size) * 0.4);
    font-weight: 700;
    line-height: 1;
    color: #111;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }

  .dash {
    width: calc(var(--size) * 0.34);
    height: calc(var(--size) * 0.08);
    background: #111;
    border-radius: 2px;
  }

  /* Three digits in the same ring. */
  .number.long {
    font-size: calc(var(--size) * 0.33);
  }

  .pulse {
    animation: pulse 0.9s ease-out;
  }

  @keyframes pulse {
    0% {
      transform: scale(1);
    }
    25% {
      transform: scale(1.18);
    }
    50% {
      transform: scale(0.96);
    }
    100% {
      transform: scale(1);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .pulse {
      animation: none;
    }
  }
</style>
