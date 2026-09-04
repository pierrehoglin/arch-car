<script lang="ts">
  import Icon from '$lib/Icon.svelte';
  import Button from '$lib/ui/Button.svelte';
  import Card from '$lib/ui/Card.svelte';
  import ScanDialog from '$lib/ui/ScanDialog.svelte';
  import Slider from '$lib/ui/Slider.svelte';
  import { play, radio, savePreset, seek, toggle, tune, watch } from '$lib/radio.svelte';

  const BAND_MIN = 87.5;
  const BAND_MAX = 108.0;

  let scanOpen = $state(false);

  /* Follow the daemon while this screen is mounted. The stream sends
     current state on connecting, so there is nothing to fetch first
     -- and RDS arriving a couple of seconds after a tune comes
     through as its own event rather than being waited for. */
  $effect(() => watch());

  const state = $derived(radio.state);
  const frequency = $derived(state.frequency ?? BAND_MIN);
  const rds = $derived(state.rds);

  const position = $derived(((frequency - BAND_MIN) / (BAND_MAX - BAND_MIN)) * 100);

  const preset = $derived(radio.presets.find((p) => Math.abs(p.frequency - frequency) < 0.01));

  /* Prefer what the station calls itself over what we saved it as:
     the preset name is a label, the PS is the broadcaster's own. */
  const name = $derived(rds.ps || preset?.name || state.name);

  /* Ticks on the band come from the last scan, so an unscanned band
     is simply blank rather than showing invented stations. */
  const found = $derived(radio.signals.map((s) => s.frequency));
</script>

<div class="tuner">
  <div class="reading">
    <span class="figure">{frequency.toFixed(1)}</span>
    <span class="unit">MHz</span>
  </div>

  <!-- Both lines hold their height whether or not there is anything
       to put in them. RDS arrives a couple of seconds after tuning,
       so an unnamed frequency is the normal state for a moment, and
       collapsing the block would jump the slider and everything below
       it every time you step through the band. -->
  <div class="station">
    <h2>{name || ' '}</h2>

    <!-- RadioText scrolls at the station's pace, so it gets a fixed
         line rather than being allowed to reflow the layout when it
         changes. -->
    <p class="radiotext">{rds.radiotext || ' '}</p>
  </div>
</div>

<div class="band">
  <span class="edge">{BAND_MIN.toFixed(1)}</span>

  <Slider
    label="Frequency"
    value={frequency}
    min={BAND_MIN}
    max={BAND_MAX}
    step={0.1}
    ticks={found}
    onchange={(f) => play(f)}
  />

  <span class="edge">{BAND_MAX.toFixed(1)}</span>
</div>

<div class="transport">
  <button class="round small" aria-label="Down 0.1" onclick={() => tune(-0.1)}>
    <Icon name="chevron-left" size={22} />
  </button>

  <button class="round" aria-label="Previous station" onclick={() => seek(-1)}>
    <Icon name="previous" size={22} />
  </button>

  <button class="round primary" aria-label={state.paused ? 'Play' : 'Pause'} onclick={toggle}>
    <Icon name={state.paused ? 'play' : 'pause'} size={30} />
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
    {#each radio.presets as item (item.frequency)}
      <button
        class="preset"
        class:current={Math.abs(item.frequency - frequency) < 0.01}
        onclick={() => play(item.frequency)}
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
    <Button
      variant="quiet"
      square
      pressed={!!preset}
      label={preset ? 'Remove from presets' : 'Save as a preset'}
      onclick={() => savePreset(frequency, name)}
    >
      <Icon name={preset ? 'star-filled' : 'star'} size={20} />
    </Button>

    <Button variant="quiet" onclick={() => (scanOpen = true)}>
      <Icon name="search" size={18} />
      Scan
    </Button>
  </div>
</Card>

<ScanDialog open={scanOpen} onclose={() => (scanOpen = false)} />

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
    height: 30px;
    margin: 0;
    overflow: hidden;
    font-size: 24px;
    font-weight: 600;
    line-height: 30px;
    white-space: nowrap;
    text-overflow: ellipsis;
    max-width: 560px;
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
    grid-template-columns: auto 1fr;
    gap: var(--spacing-s);
  }

  /* A saved station gets the accent, so the state reads without the
     word that used to carry it. */
</style>
