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
     
     untrack, because scan() reads radio.scanning through its own
     guard -- without it the effect depends on that flag, re-runs when
     the scan sets it false on finishing, and starts another scan
     immediately. It never stops. */
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
      const named = Number(!!b.rds_name) - Number(!!a.rds_name)
      return named || a.frequency - b.frequency
    }),
  )

  const identified = $derived(found.filter((s) => s.rds_name).length)

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
  {#if radio.scanning}
    <div class="working">
      <Spinner label="Scanning" />
      <p class="what">Sweeping the band</p>
      <p class="detail">
        Each station found is tuned in turn to read its name, so this
        takes a few seconds. Playback resumes afterwards.
      </p>
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
            <!-- Unnamed stations show the frequency as their name,
                 rather than an empty line where a name would be. -->
            <span class="name">
              {station.rds_name || `${station.frequency.toFixed(1)} MHz`}
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

          <Button
            variant={playing ? 'primary' : 'plain'}
            square
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
    {#if !radio.scanning}
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

  .summary {
    margin-right: auto;
    font-size: 13px;
    color: var(--text-dim);
  }


</style>
