<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Button from '$lib/ui/Button.svelte'
  import Card from '$lib/ui/Card.svelte'
  import PresetDialog from '$lib/ui/PresetDialog.svelte'
  import ScanDialog from '$lib/ui/ScanDialog.svelte'
  import Sortable from '$lib/ui/Sortable.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import Slider from '$lib/ui/Slider.svelte'
  import {
    play,
    radio,
    reorderPresets,
    savePreset,
    seek,
    toggle,
    tune,
    loadPresets,
    refresh,
    watch,
  } from '$lib/radio.svelte'
  import type { Station } from '$lib/api/types'
  import { logoForPi, nameForPi } from '$lib/stations'
  import { isDark } from '$lib/settings.svelte'

  const BAND_MIN = 87.5
  const BAND_MAX = 108.0

  let scanOpen = $state(false)

  /* Where the thumb is while it is being dragged.
   *
   * Retuning restarts the pipeline, so doing it per pixel would be
   * unusable -- the reading follows the thumb and the radio only
   * moves when it is let go. Null when nobody is dragging. */
  let dragging = $state<number | null>(null)

  /* The preset being edited, or null. Holding a chip opens this;
     holding and dragging reorders instead. */
  let editing = $state<Station | null>(null)

  /* Follow the daemon while this screen is mounted. The stream sends
     current state on connecting, so there is nothing to fetch first
     -- and RDS arriving a couple of seconds after a tune comes
     through as its own event rather than being waited for. */
  /* Fetched as well as watched. The stream replays what it has
     cached, but a screen that opened before the daemon had published
     anything would sit empty -- and presets are published once, at
     startup, so "before" is easy to be. */
  $effect(() => {
    refresh()
    loadPresets()
    return watch()
  })

  const state = $derived(radio.state)

  /* Whether anything is actually coming out. The pipeline running
     and not muted -- either being false means silence, and the
     button should offer to start it. */
  const sounding = $derived(state.playing && !state.paused)
  /* What the dial reads, in order: the thumb if a finger is on it,
     then where a retune is heading, then where the radio actually
     is, then where it would come back on.
     
     The last of those is what a stopped radio shows. Falling
     straight to the bottom of the band would say 87.5 about a car
     that was on 107.4 yesterday -- and pressing play would then jump
     somewhere else, because the daemon resumes from the same place
     this is reading. */
  const frequency = $derived(
    dragging ?? radio.pending ?? state.frequency ?? state.last ?? BAND_MIN,
  )
  const rds = $derived(state.rds)

  /* Only once the dial has settled. While the thumb is moving, or
     the pipeline is restarting, the PI still belongs to the
     station being left -- and its logo over the new frequency
     would be the wrong answer twice over. */
  const logo = $derived(
    dragging === null && !radio.busy
      ? logoForPi(rds.pi, isDark())
      : '',
  )

  const preset = $derived(
    radio.presets.find((p) => Math.abs(p.frequency - frequency) < 0.01),
  )

  /* Prefer what the station calls itself over what we saved it as:
     the preset name is a label, the PS is the broadcaster's own.
     
     The PI code sits between them. It decodes within a second of
     tuning, well before PS has assembled, so it fills the gap where
     a station would otherwise be nameless -- and it is right about
     stations nobody has saved.

     While the thumb is moving, the RDS belongs to the station still
     playing and has nothing to do with the frequency under the
     finger -- so only a saved name is shown, and usually nothing. */
  const name = $derived(
    dragging !== null
      ? (preset?.name ?? '')
      : rds.ps || preset?.name || nameForPi(rds.pi) || state.name,
  )

  /* Ticks on the band come from the last scan, so an unscanned band
     is simply blank rather than showing invented stations. */
  const found = $derived(radio.signals.map((s) => s.frequency))
</script>

<div class="tuner">
  <!-- The logo takes the place of the number, not a space beside
       it: both say which station this is, and the frequency is
       the answer only until something better arrives. Away from a
       logo -- dragging, retuning, or a station without one -- the
       number comes back. -->
  <div class="reading">
    {#if logo}
      <img class="mark" src={logo} alt={name} />
    {:else}
      <!-- Grouped, so the pair can share a baseline while the
           group as a whole sits at the foot of the box. -->
      <span class="numbers">
        <span class="figure">{frequency.toFixed(1)}</span>
        <span class="unit">MHz</span>
      </span>
    {/if}
  </div>

  <!-- Both lines hold their height whether or not there is anything
       to put in them. RDS arrives a couple of seconds after tuning,
       so an unnamed frequency is the normal state for a moment, and
       collapsing the block would jump the slider and everything below
       it every time you step through the band. -->
  <div class="station">
    <!-- A ring where the name goes, while the pipeline restarts.
         The frequency above has already moved, which says what is
         happening; this says it is not finished yet. -->
    {#if radio.busy}
      <h2 class="tuning">
        <Spinner size={26} label="Tuning" />
      </h2>
    {:else}
      <h2>{name || ' '}</h2>
    {/if}

    <!-- RadioText scrolls at the station's pace, so it gets a fixed
         line rather than being allowed to reflow the layout when it
         changes.

         Blank while moving or retuning: it belongs to the station
         being left behind. -->
    <p class="radiotext">
      {dragging !== null || radio.busy ? ' ' : rds.radiotext || ' '}
    </p>
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
    disabled={radio.busy}
    oninput={(f) => (dragging = f)}
    onchange={(f) => {
      dragging = null
      play(f)
    }}
  />

  <span class="edge">{BAND_MAX.toFixed(1)}</span>
</div>

<div class="transport">
  <button
    class="round small"
    aria-label="Down 0.1"
    disabled={radio.busy}
    onclick={() => tune(-0.1)}
  >
    <Icon name="chevron-left" size={22} />
  </button>

  <button
    class="round"
    aria-label="Previous station"
    disabled={radio.busy}
    onclick={() => seek(-1)}
  >
    <Icon name="previous" size={22} />
  </button>

  <!-- Three states, not two. `paused` only means anything while the
       radio is running: stopped, it is false, which read on its own
       says "playing" about a radio that is off. -->
  <button
    class="round primary"
    aria-label={sounding ? 'Pause' : 'Play'}
    disabled={radio.busy}
    onclick={toggle}
  >
    <Icon name={sounding ? 'pause' : 'play'} size={30} />
  </button>

  <button
    class="round"
    aria-label="Next station"
    disabled={radio.busy}
    onclick={() => seek(1)}
  >
    <Icon name="next" size={22} />
  </button>

  <button
    class="round small"
    aria-label="Up 0.1"
    disabled={radio.busy}
    onclick={() => tune(0.1)}
  >
    <Icon name="chevron-right" size={22} />
  </button>
</div>

<Card eyebrow="Presets" gap="s" class="preset-card">
  <!-- Hold a preset to edit it; hold and drag to reorder. Tapping
       plays it. -->
  <Sortable
    class="presets"
    items={radio.presets}
    key={(item) => item.frequency}
    onactivate={(item) => play(item.frequency)}
    onhold={(item) => (editing = item)}
    onreorder={(next) => reorderPresets(next)}
    label={(item) =>
      `${item.name || 'Preset'}, ${item.frequency.toFixed(1)} megahertz`}
  >
    {#snippet item(entry: Station)}
      <div
        class="preset"
        class:current={Math.abs(entry.frequency - frequency) < 0.01}
      >
        <span class="preset-name">
          {entry.name || entry.frequency.toFixed(1)}
        </span>
        <span class="preset-frequency">{entry.frequency.toFixed(1)}</span>
      </div>
    {/snippet}
  </Sortable>

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

<PresetDialog preset={editing} onclose={() => (editing = null)} />

<style>
  .tuner {
    /* Taller than the frequency needs, so a logo has room to be
       a logo rather than a line of type. The number keeps its
       own size and sits at the foot of the box; the space above
       it is where a tall logo goes. */
    --reading: 94px;
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

  /* Fixed height, because what goes in it changes.
     
     A logo is whatever shape it was drawn, and a short one would
     make this block shorter than the number it replaced -- taking
     the slider, the transport and the presets up with it every time
     RDS decoded or a station changed. */
  .reading {
    display: flex;
    align-items: flex-end;
    justify-content: center;
    height: var(--reading);
  }

  .numbers {
    display: flex;
    align-items: baseline;
    gap: var(--spacing-xs);
  }

  /* Drawn to the height of the number it replaces, so the block does
     not jump between a station with a logo and one without. Wide is
     fine; tall is not. */
  .mark {
    /* Centred, not at the foot with the number. A logo is a shape
       rather than a line of type: sitting it on the same line would
       leave a short one stranded under a tall gap. */
    align-self: center;

    /* An explicit height, not a maximum.
       
       An SVG with only a viewBox has no intrinsic size, so an `img`
       constrained by max-height alone resolves to nothing and the
       logo vanishes. Giving the height outright means the browser
       has something to scale the viewBox against.
       
       Width follows the aspect ratio until it hits the cap, and
       `contain` keeps the shape when it does -- so a very wide
       wordmark is letterboxed rather than squashed. */
    height: var(--reading);
    width: auto;
    max-width: 420px;
    object-fit: contain;
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


  /* Stands in for the name, and holds its height so the block does
     not shift when the station arrives. No word beside it: the
     frequency above has already changed, which says what is
     happening, and the ring says it is not finished. */
  .tuning {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
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

  /* Dimmed while the pipeline restarts, so a press that does nothing
     looks like one that was not going to. */
  .round:disabled {
    opacity: 0.4;
    cursor: default;
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

  /* Four columns rather than a wrapping row. With presets of very
     different name lengths, wrapping gave three ragged rows; fixed
     columns keep the chips a consistent size and the rows even.
     
     Sortable reads these as variables, since it owns the container. */
  .preset-card :global(.presets) {
    --columns: repeat(4, 1fr);
    --gap: var(--spacing-s);
  }

  /* Presentational: Sortable's slot is the control, and carries the
     focus ring and the spoken label. */
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
