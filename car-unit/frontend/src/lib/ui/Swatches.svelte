<script lang="ts">
  import { accentFor } from '$lib/accent'
  import { SWATCH_NAMES, SWATCHES, type Theme } from '$lib/types'

  interface Props {
    value: string
    theme: Theme
    onchange: (value: string) => void
  }

  let { value, theme, onchange }: Props = $props()

  /* Each swatch shows the variant it would actually become, not its
     canonical hex. Otherwise blue's swatch would look identical on
     both themes while producing two different accents. */
  const shown = $derived(
    SWATCHES.map((base) => ({ base, colour: accentFor(base, theme) })),
  )

</script>

<div class="swatches" role="radiogroup" aria-label="Cabin accent colour">
  {#each shown as swatch (swatch.base)}
    <button
      class="swatch"
      class:selected={value === swatch.base}
      style:--swatch={swatch.colour}
      role="radio"
      aria-checked={value === swatch.base}
      aria-label={SWATCH_NAMES[swatch.base] ?? swatch.base}
      onclick={() => onchange(swatch.base)}
    ></button>
  {/each}
</div>

<style>
  .swatches {
    display: flex;
    gap: var(--spacing-s);
  }

  .swatch {
    position: relative;
    width: 30px;
    height: 30px;
    padding: 0;
    background: var(--swatch);
    border: 0;
    border-radius: 50%;
    /* The hit area is larger than the dot. Thirty pixels is right
       visually and much too small for a thumb in a moving car. */
    outline-offset: 0;
  }

  .swatch::after {
    content: '';
    position: absolute;
    inset: -9px;
  }

  /* A ring rather than a tick: the selected colour stays fully
     visible, which is the thing being chosen. */
  .swatch.selected {
    box-shadow:
      0 0 0 2px var(--surface),
      0 0 0 4px var(--swatch);
  }

  .swatch:focus-visible {
    box-shadow:
      0 0 0 2px var(--surface),
      0 0 0 4px var(--text);
  }
</style>
