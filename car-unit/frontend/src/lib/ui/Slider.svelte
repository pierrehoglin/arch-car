<script lang="ts">
  interface Props {
    value: number
    min?: number
    max?: number
    step?: number
    label?: string
    /** Shown to the left of the track, e.g. "72%". */
    readout?: string

    /** Every movement, for anything cheap to apply. */
    oninput?: (value: number) => void
    /** Only when the thumb is let go.
     *
     *  Use this where a change costs something -- retuning the radio
     *  restarts the pipeline, and doing that per pixel of a drag
     *  would be unusable. */
    onchange?: (value: number) => void

    /** Values to mark below the track. For a band with known
     *  stations on it. */
    ticks?: number[]
  }

  let {
    value,
    min = 0,
    max = 100,
    step = 1,
    label = '',
    readout = '',
    oninput,
    onchange,
    ticks = [],
  }: Props = $props()

  const share = (of: number) => ((of - min) / (max - min)) * 100
  const fill = $derived(share(value))

  /* A tick counts as "here" within half a step, so the marker lights
     for the station being received rather than only on an exact
     floating-point match. */
  const here = (tick: number) => Math.abs(tick - value) < step / 2
</script>

<div class="slider">
  {#if readout}
    <span class="readout">{readout}</span>
  {/if}

  <div class="track">
    <input
      type="range"
      {min}
      {max}
      {step}
      {value}
      aria-label={label}
      style:--fill="{fill}%"
      oninput={(e) => oninput?.(+e.currentTarget.value)}
      onchange={(e) => onchange?.(+e.currentTarget.value)}
    />

    {#if ticks.length}
      <div class="ticks" aria-hidden="true">
        {#each ticks as tick (tick)}
          <i style:left="{share(tick)}%" class:here={here(tick)}></i>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .slider {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    width: 100%;
  }

  .readout {
    min-width: 42px;
    font-size: 14px;
    text-align: right;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .track {
    flex: 1;
    min-width: 0;
  }

  input {
    display: block;
    width: 100%;
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

  .ticks {
    position: relative;
    height: 10px;
    margin-top: 6px;
  }

  .ticks i {
    position: absolute;
    top: 0;
    width: 2px;
    height: 6px;
    background: var(--text-faint);
    transform: translateX(-50%);
  }

  .ticks i.here {
    height: 10px;
    background: var(--accent);
  }
</style>
