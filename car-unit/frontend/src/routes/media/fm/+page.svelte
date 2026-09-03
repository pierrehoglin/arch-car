<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Card from '$lib/ui/Card.svelte'

  /* Placeholder throughout. Nothing is wired to the daemon.
   *
   * Shaped around what carlib.radio.fm actually provides: tune in
   * 0.1 MHz steps, seek to the next station a scan found, presets,
   * and the RDS payload -- station name, radiotext, programme type,
   * alternative frequencies, and the traffic flags. */

  const BAND_MIN = 87.5
  const BAND_MAX = 108.0

  let frequency = $state(107.4)
  let playing = $state(true)

  /* What a band scan turned up. Real ones come from rtl_power with a
     local noise floor; these are the peaks from a sweep in
     Sundsvall. */
  const found = [92.7, 96.3, 96.9, 99.2, 101.9, 102.8, 107.4]

  /* Eight, to see how the row wraps. Real Swedish stations, since
     name lengths are the thing being tested -- "Sveriges Radio P2"
     and "NRJ" set very different widths. */
  const presets = [
    { frequency: 92.7, name: 'P3' },
    { frequency: 96.3, name: 'NRJ' },
    { frequency: 96.9, name: 'P2' },
    { frequency: 99.2, name: 'Mix Megapol' },
    { frequency: 101.9, name: 'Rockklassiker' },
    { frequency: 102.8, name: 'Bandit Rock' },
    { frequency: 105.7, name: 'P4 Stockholm' },
    { frequency: 107.4, name: 'RIX FM' },
  ]

  /* Only what the screen shows. RDS carries a good deal more --
     programme type, traffic flags, alternative frequencies, the
     group count -- and the backend decodes all of it, but none of it
     earns space here.
     
     Both of these fill in over several seconds as groups repeat, so
     both are empty for a moment after tuning. */
  const rds = $state({
    ps: 'RIX FM',
    radiotext: 'Bäst musik just nu!',
  })

  const position = $derived(
    ((frequency - BAND_MIN) / (BAND_MAX - BAND_MIN)) * 100,
  )

  const preset = $derived(
    presets.find((p) => Math.abs(p.frequency - frequency) < 0.01),
  )

  /* Prefer what the station calls itself over what we saved it as:
     the preset name is a label, the PS is the broadcaster's own. */
  const name = $derived(rds.ps || preset?.name || '')

  const tune = (step: number) => {
    const next = Math.round((frequency + step) * 10) / 10
    frequency = next > BAND_MAX ? BAND_MIN : next < BAND_MIN ? BAND_MAX : next
  }

  const seek = (direction: number) => {
    const ordered = direction > 0 ? found : [...found].reverse()
    frequency =
      ordered.find((f) =>
        direction > 0 ? f > frequency + 0.05 : f < frequency - 0.05,
      ) ?? ordered[0]
  }
</script>

<div class="tuner">
  <div class="reading">
    <span class="figure">{frequency.toFixed(1)}</span>
    <span class="unit">MHz</span>
  </div>

  <div class="station">
    {#if name}
      <h2>{name}</h2>
    {/if}

    <!-- RadioText scrolls at the station's pace, so it gets a fixed
         line rather than being allowed to reflow the layout when it
         changes. -->
    <p class="radiotext">{rds.radiotext || ' '}</p>
  </div>
</div>

<div class="band">
  <span class="edge">{BAND_MIN.toFixed(1)}</span>

  <div class="dial">
    <input
      type="range"
      min={BAND_MIN}
      max={BAND_MAX}
      step="0.1"
      value={frequency}
      style:--fill="{position}%"
      aria-label="Frequency"
      oninput={(e) => (frequency = +e.currentTarget.value)}
    />

    <!-- Where a scan found something, so the band reads as places
         rather than a blank range. -->
    <div class="ticks" aria-hidden="true">
      {#each found as station (station)}
        <i
          style:left="{((station - BAND_MIN) / (BAND_MAX - BAND_MIN)) * 100}%"
          class:here={Math.abs(station - frequency) < 0.05}
        ></i>
      {/each}
    </div>
  </div>

  <span class="edge">{BAND_MAX.toFixed(1)}</span>
</div>

<div class="transport">
  <button class="round small" aria-label="Down 0.1" onclick={() => tune(-0.1)}>
    <Icon name="chevron-left" size={22} />
  </button>

  <button class="round" aria-label="Previous station" onclick={() => seek(-1)}>
    <Icon name="previous" size={22} />
  </button>

  <button
    class="round primary"
    aria-label={playing ? 'Pause' : 'Play'}
    onclick={() => (playing = !playing)}
  >
    <Icon name={playing ? 'pause' : 'play'} size={30} />
  </button>

  <button class="round" aria-label="Next station" onclick={() => seek(1)}>
    <Icon name="next" size={22} />
  </button>

  <button class="round small" aria-label="Up 0.1" onclick={() => tune(0.1)}>
    <Icon name="chevron-right" size={22} />
  </button>
</div>

<Card eyebrow="Presets" gap="s" class="preset-card">
  <div class="presets">
    {#each presets as item (item.frequency)}
      <button
        class="preset"
        class:current={Math.abs(item.frequency - frequency) < 0.01}
        onclick={() => (frequency = item.frequency)}
      >
        <span class="preset-name">{item.name}</span>
        <span class="preset-frequency">{item.frequency.toFixed(1)}</span>
      </button>
    {/each}
  </div>

  <!-- Both of these act on what is playing rather than jumping
       somewhere, so they sit below the grid rather than in it. -->
  <div class="actions">
    <!-- Icon only, so it needs the label spoken instead. The filled
         star already says whether this station is saved. -->
    <button
      class="action star"
      aria-label={preset ? 'Remove from presets' : 'Save as a preset'}
      aria-pressed={!!preset}
    >
      <Icon name={preset ? 'star-filled' : 'star'} size={20} />
    </button>

    <button class="action">
      <Icon name="search" size={18} />
      Scan
    </button>
  </div>
</Card>

<style>
  .tuner {
    display: flex;
    flex-direction: column;
    align-items: center;
    /* The gap between the frequency and the station block. Wider
       than the one inside that block, so the two read as separate
       things rather than one list. */
    gap: var(--spacing-l);
  }

  .station {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .reading {
    display: flex;
    align-items: baseline;
    gap: var(--spacing-xs);
  }

  /* The frequency is what this screen is for, so it gets the size the
     clock gets on the dashboard. */
  .figure {
    font-family: var(--font-display);
    font-size: 64px;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .unit {
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-dim);
  }

  h2 {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
  }



  .radiotext {
    /* A fixed line: RadioText changes with the song, and letting it
       wrap would shift everything below it every few minutes. */
    height: 20px;
    margin: 0;
    max-width: 560px;
    overflow: hidden;
    font-size: 15px;
    color: var(--text-dim);
    text-align: center;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .band {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    width: 100%;
    max-width: 560px;
  }

  .edge {
    font-size: 12px;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .dial {
    position: relative;
    flex: 1;
  }

  input[type='range'] {
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

  input[type='range']::-webkit-slider-thumb {
    appearance: none;
    width: 20px;
    height: 20px;
    background: var(--knob);
    border-radius: 50%;
  }

  input[type='range']::-moz-range-thumb {
    width: 20px;
    height: 20px;
    background: var(--knob);
    border: 0;
    border-radius: 50%;
  }

  input[type='range']:focus-visible {
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

  .transport {
    display: flex;
    align-items: center;
    gap: var(--spacing);
  }

  .round {
    display: grid;
    place-items: center;
    width: 68px;
    height: 68px;
    color: var(--text);
    background: var(--panel-2);
    border: 0;
    border-radius: 50%;
  }

  /* Tuning by a tenth is the fine adjustment, so its buttons sit
     outside the seek pair and read smaller. */
  .round.small {
    width: 52px;
    height: 52px;
    color: var(--text-dim);
  }

  .round.primary {
    width: 92px;
    height: 92px;
    color: var(--accent-ink);
    background: var(--accent);
  }

  .round:active {
    filter: brightness(0.92);
  }

  .round:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }

  /* The card is as wide as the band above it, so the two line up
     rather than the presets floating at their own width. */
  .tuner ~ :global(.preset-card) {
    width: 100%;
    max-width: 560px;
  }

  /* A grid rather than a wrapping row. With eight presets of very
     different name lengths, wrapping gave three ragged rows and left
     the save button stranded on its own; fixed columns keep the
     chips a consistent size and the rows even. */
  .presets {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--spacing-s);
  }

  .preset {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    min-width: 0;
    min-height: 54px;
    padding: 0 var(--spacing-s);
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .preset.current {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .preset:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Truncate rather than wrap: a two-line chip would make its row
     taller than the others. */
  .preset-name {
    max-width: 100%;
    overflow: hidden;
    font-size: 15px;
    font-weight: 600;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .preset-frequency {
    font-size: 12px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .actions {
    display: grid;
    /* The star is a fixed square; scan takes the rest. */
    grid-template-columns: 54px 1fr;
    gap: var(--spacing-s);
  }

  .action {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-xs);
    min-height: 46px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-dim);
    background: none;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .star.action {
    padding: 0;
  }

  /* A saved station gets the accent, so the state reads without the
     word that used to carry it. */
  .star[aria-pressed='true'] {
    color: var(--accent);
    border-color: var(--accent);
  }

  .action:active {
    background: var(--panel-2);
  }

  .action:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }



</style>
