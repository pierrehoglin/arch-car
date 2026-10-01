<script lang="ts">
  import { untrack } from 'svelte'
  import Icon from '../Icon.svelte'
  import Button from './Button.svelte'
  import Dialog from './Dialog.svelte'
  import Spinner from './Spinner.svelte'
  import {
    loadPresets,
    play,
    radio,
    savePreset,
    scan,
  } from '../radio.svelte'
  import { nameForPi } from '../stations'

  interface Props {
    open: boolean
    onclose: () => void
  }

  let { open, onclose }: Props = $props()

  /* Whether a frequency is already saved, so the star shows state
     rather than only offering an action. */
  const saved = (frequency: number) =>
    radio.presets.some((p) => Math.abs(p.frequency - frequency) < 0.01)

  /* Start a sweep whenever the dialog opens. Opening it is the
     request; a second button inside would be a step for nothing.
     
     untrack because of the presets check below, which reads state the
     call it guards then changes. scan() no longer needs it -- its own
     guard is a plain flag -- but leaving the block untracked keeps
     the two from having to be reasoned about separately. */
  $effect(() => {
    if (open) {
      untrack(() => {
        scan(true)
        // The stars need these to show what is already saved, and the
        // dialog can be opened before a screen has fetched them.
        if (!radio.presets.length) loadPresets()
      })
    }
  })

  const found = $derived(radio.signals)

  /* Identified stations first, then by frequency. A peak with no RDS
     is usually noise or too weak to be worth tuning, so it should not
     sit above a real station just because it is lower down the
     band. */
  const ordered = $derived(
    [...found].sort((a, b) => {
      const named =
        Number(!!(b.rds_name || nameForPi(b.pi))) -
        Number(!!(a.rds_name || nameForPi(a.pi)))
      return named || a.frequency - b.frequency
    }),
  )

  /* Named either way: by what it called itself, or by its PI. A
     station recognised from its code is identified as much as one
     that announced itself. */
  const identified = $derived(
    found.filter((s) => s.rds_name || nameForPi(s.pi)).length,
  )

  /* Seconds since the scan began, for the footer while it runs.
     From the daemon's start time rather than from opening the dialog,
     so a scan already under way shows how long it has really taken. */
  let now = $state(Date.now() / 1000)

  $effect(() => {
    if (!radio.scanning) return
    now = Date.now() / 1000
    const timer = setInterval(() => (now = Date.now() / 1000), 1000)
    return () => clearInterval(timer)
  })

  const progress = $derived(radio.progress)

  const elapsed = $derived.by(() => {
    const seconds = Math.max(0, Math.round(now - (progress?.started ?? now)))
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  })

  /** Where one frequency is in the listening pass. */
  function stepOf(index: number, frequency: number) {
    if (!progress) return 'waiting'
    if (index < progress.checked) return 'done'
    if (progress.current === frequency) return 'listening'
    return 'waiting'
  }

  /** Signal strength as five steps, 0 to 30 dB over the noise floor. */
  const bars = (power: number) =>
    Math.min(5, Math.max(0, Math.round(power / 6)))
</script>

<Dialog
  {open}
  {onclose}
  title="Scan"
  dismissable={!radio.scanning}
>
  {#if radio.scanning && progress?.phase === 'identifying'}
    <!-- Every peak the sweep found, in the order they are listened
         to. Up the band rather than strongest first, so the one being
         listened to moves steadily down the list instead of jumping
         about. -->
    <div class="pass">
      <div class="pass-head">
        <span>Reading station names</span>
        <span class="pass-count">
          {progress.checked} of {progress.signals.length}
        </span>
      </div>
      <div
        class="bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={progress.signals.length}
        aria-valuenow={progress.checked}
      >
        <i style:width="{(progress.checked / progress.signals.length) * 100}%"
        ></i>
      </div>
    </div>

    <ul class="stations">
      {#each progress.signals as station, index (station.frequency)}
        {@const step = stepOf(index, station.frequency)}
        {@const named = station.rds_name || nameForPi(station.pi)}
        <li
          class="station"
          class:waiting={step === 'waiting'}
          class:listening={step === 'listening'}
        >
          <span class="strength" aria-hidden="true">
            {#each [1, 2, 3, 4, 5] as level (level)}
              <i
                class:lit={level <= bars(station.power)}
                style:height="{2 + level * 2}px"
              ></i>
            {/each}
          </span>

          <span class="labels">
            <span class="name">
              {step === 'done' && named
                ? named
                : `${station.frequency.toFixed(1)} MHz`}
            </span>
            <span class="frequency" class:faint={step !== 'listening' && !(step === 'done' && named)}>
              {#if step === 'listening'}
                Listening for RDS
              {:else if step === 'waiting'}
                Waiting
              {:else if named}
                {station.frequency.toFixed(1)} MHz
              {:else}
                No RDS — probably noise
              {/if}
            </span>
          </span>

          <span class="state" aria-hidden="true">
            {#if step === 'listening'}
              <Spinner size={18} label="Listening" />
            {:else if step === 'done' && named}
              <Icon name="check" size={20} />
            {/if}
          </span>
        </li>
      {/each}
    </ul>
  {:else if radio.scanning}
    <div class="working">
      <Spinner label="Scanning" />
      {#if progress?.phase === 'resuming'}
        <p class="what">Resuming playback</p>
        <p class="detail">
          {progress.signals.length} found. Back to what was playing.
        </p>
      {:else}
        <p class="what">Sweeping the band</p>
        <p class="detail">
          Measuring signal strength from 87.5 to 108 MHz. Each peak is
          then tuned in turn to read its name, and playback resumes
          afterwards.
        </p>
      {/if}
    </div>
  {:else if radio.error}
    <div class="working">
      <p class="what">Scan failed</p>
      <p class="detail">{radio.error}</p>
    </div>
  {:else if !ordered.length}
    <div class="working">
      <p class="what">Nothing found</p>
      <p class="detail">
        Check the aerial is connected. A scan needs a stronger signal
        than listening does.
      </p>
    </div>
  {:else}
    <ul class="stations">
      {#each ordered as station (station.frequency)}
        {@const playing = radio.state.frequency === station.frequency}
        <li class="station" class:playing>
          <span class="strength" aria-hidden="true">
            {#each [1, 2, 3, 4, 5] as level (level)}
              <i
                class:lit={level <= bars(station.power)}
                style:height="{2 + level * 2}px"
              ></i>
            {/each}
          </span>

          <span class="labels">
            <!-- The PI code stands in where the name did not
                 decode: a scan gives each station only a second or
                 two, which is often enough for the identifier and
                 not for the name. Failing both, the frequency --
                 rather than an empty line where a name would be. -->
            <span class="name">
              {station.rds_name ||
                nameForPi(station.pi) ||
                `${station.frequency.toFixed(1)} MHz`}
            </span>
            {#if station.rds_name}
              <span class="frequency">
                {station.frequency.toFixed(1)} MHz
              </span>
            {:else}
              <span class="frequency faint">No RDS — probably noise</span>
            {/if}
          </span>

          <!-- Two explicit actions rather than a row that tunes when
               tapped: with a star beside it, a whole-row target would
               make it a guess which one you hit. -->
          <Button
            variant="quiet"
            square
            pressed={saved(station.frequency)}
            label={saved(station.frequency)
              ? `${station.frequency.toFixed(1)} is saved`
              : `Save ${station.frequency.toFixed(1)}`}
            onclick={() =>
              savePreset(station.frequency, station.rds_name)}
          >
            <Icon
              name={saved(station.frequency) ? 'star-filled' : 'star'}
              size={20}
            />
          </Button>

          <!-- Held while the pipeline restarts: the dongle takes one
               process at a time, and a second tune before the first
               has released it fails outright. -->
          <Button
            variant={playing ? 'primary' : 'plain'}
            square
            disabled={radio.busy}
            label="Listen to {station.frequency.toFixed(1)}"
            onclick={() => play(station.frequency)}
          >
            <Icon name={playing ? 'volume' : 'play'} size={20} />
          </Button>
        </li>
      {/each}
    </ul>
  {/if}

  {#snippet footer()}
    {#if radio.scanning}
      <span class="summary">Scanning · {elapsed}</span>
    {:else}
      <span class="summary">
        {#if ordered.length}
          {ordered.length} found, {identified} named
        {/if}
      </span>
      <Button variant="quiet" onclick={() => scan(true)}>
        Scan again
      </Button>
      <Button variant="primary" onclick={onclose}>Close</Button>
    {/if}
  {/snippet}
</Dialog>

<style>
  .working {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--spacing-s);
    padding: var(--spacing-xl) var(--spacing) var(--spacing-l);
    text-align: center;
  }



  .what {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
  }

  .detail {
    max-width: 40ch;
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-dim);
  }

  .stations {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .station {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    min-height: 68px;
    padding: var(--spacing-xs) 0;
    border-bottom: 1px solid var(--hairline);
  }

  .station:last-child {
    border-bottom: 0;
  }

  .station.playing .name {
    color: var(--accent);
  }

  .strength {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    width: 22px;
    height: 12px;
  }

  .strength i {
    width: 3px;
    border-radius: 1px;
    background: var(--border);
  }

  .strength i.lit {
    background: currentColor;
  }

  .labels {
    display: flex;
    flex-direction: column;
    gap: 1px;
    flex: 1;
    min-width: 0;
  }

  .name {
    font-size: 16px;
    font-weight: 600;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .frequency {
    font-size: 12.5px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .frequency.faint {
    color: var(--text-faint);
  }

  .pass {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    padding-bottom: var(--spacing-s);
  }

  .pass-head {
    display: flex;
    justify-content: space-between;
    font-size: 14px;
    font-weight: 600;
  }

  .pass-count {
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .bar {
    height: 4px;
    overflow: hidden;
    background: var(--chip);
    border-radius: 2px;
  }

  .bar i {
    display: block;
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.3s ease;
  }

  /* Not yet listened to: there, but not the point yet. */
  .station.waiting {
    opacity: 0.45;
  }

  .station.listening .name {
    color: var(--accent);
  }

  /* A fixed slot, so rows do not shift as the spinner moves down and
     ticks appear. */
  .state {
    display: grid;
    place-items: center;
    width: 46px;
    color: var(--accent);
  }

  .summary {
    margin-right: auto;
    font-size: 13px;
    color: var(--text-dim);
  }


</style>
