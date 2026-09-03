<script lang="ts">
  interface Props {
    value: number
    onchange: (value: number) => void
    min?: number
    max?: number
    label?: string
    /** Shown to the left of the track, e.g. "72%". */
    readout?: string
  }

  let {
    value,
    onchange,
    min = 0,
    max = 100,
    label = '',
    readout = '',
  }: Props = $props()

  const fill = $derived(((value - min) / (max - min)) * 100)
</script>

{#if readout}
  <span class="readout">{readout}</span>
{/if}

<input
  type="range"
  {min}
  {max}
  {value}
  aria-label={label}
  style:--fill="{fill}%"
  oninput={(e) => onchange(+e.currentTarget.value)}
/>

<style>
  .readout {
    min-width: 42px;
    font-size: 14px;
    text-align: right;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  input {
    width: 260px;
    height: 8px;
    appearance: none;
    border-radius: 4px;
    background: linear-gradient(
      to right,
      var(--accent) var(--fill),
      var(--border) var(--fill)
    );
  }

  input::-webkit-slider-thumb {
    appearance: none;
    width: 22px;
    height: 22px;
    background: var(--knob);
    border-radius: 50%;
  }

  input::-moz-range-thumb {
    width: 22px;
    height: 22px;
    background: var(--knob);
    border: 0;
    border-radius: 50%;
  }

  input:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 6px;
  }
</style>
