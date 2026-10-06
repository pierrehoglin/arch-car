<script lang="ts">
  import Icon from '../Icon.svelte'
  import Spinner from '../ui/Spinner.svelte'
  import {
    choose,
    dismiss,
    end,
    removeStop,
    retry,
    trip,
  } from '../route.svelte'

  /* The route: where it goes, through where, how far and how long.

     Above the pin card in the bottom-left column, and like it anchored
     at its foot, so it grows upwards as stops are added. Shown as soon
     as a route is asked for, so the wait and any failure have somewhere
     to be said. */

  interface Props {
    /** Start guidance. Not connected yet -- the next step. */
    onstart: () => void
  }

  let { onstart }: Props = $props()

  /* The destination being shown: the route's, or while the first one
     is still being asked for, the one asked for. */
  const destination = $derived(trip.destination ?? trip.pending?.destination)
  const route = $derived(trip.options[trip.chosen])

  /* Arrival moves with the clock even when the route does not. */
  let now = $state(Date.now())
  $effect(() => {
    const timer = setInterval(() => (now = Date.now()), 30_000)
    return () => clearInterval(timer)
  })

  function distance(metres: number): string {
    if (metres < 1000) return `${Math.round(metres / 10) * 10} m`
    if (metres < 100_000) return `${(metres / 1000).toFixed(1)} km`
    return `${Math.round(metres / 1000)} km`
  }

  function duration(seconds: number): string {
    const minutes = Math.max(1, Math.round(seconds / 60))
    if (minutes < 60) return `${minutes} min`
    const hours = Math.floor(minutes / 60)
    return `${hours} h ${String(minutes % 60).padStart(2, '0')} min`
  }

  /* From now rather than from when it was planned: a route looked at
     for ten minutes before leaving should not promise an arrival ten
     minutes early. */
  const arrival = $derived(
    route
      ? new Date(now + route.time * 1000).toLocaleTimeString('sv-SE', {
          hour: '2-digit',
          minute: '2-digit',
        })
      : '',
  )
</script>

{#if destination}
  <section class="card" aria-label="Route">
    <header>
      <span class="mark">
        <Icon name="directions" size={20} />
      </span>
      <div class="what">
        <span class="eyebrow">Route to</span>
        <span class="title">{destination.title}</span>
        {#if destination.subtitle}
          <span class="subtitle">{destination.subtitle}</span>
        {/if}
      </div>
      <!-- Dropping the route, in the corner as on the navigation card,
           so Start has the whole width. -->
      <button class="end" aria-label="End route" onclick={end}>
        <Icon name="trash" size={20} />
      </button>
    </header>

    {#if trip.stops.length}
      <ol class="stops">
        {#each trip.stops as stop, index (index)}
          <li>
            <span class="number">{index + 1}</span>
            <span class="stop-name">
              {stop.title}{stop.subtitle ? `, ${stop.subtitle}` : ''}
            </span>
            <button
              class="remove"
              aria-label="Remove stop {index + 1}"
              disabled={trip.planning}
              onclick={() => removeStop(index)}
            >
              <Icon name="close" size={16} />
            </button>
          </li>
        {/each}
      </ol>
    {/if}

    <!-- The ways there, by how long each takes. The same as tapping a
         grey line on the map. Only when there is a choice: the router
         offers none through stops. -->
    {#if trip.options.length > 1}
      <div class="options" role="group" aria-label="Ways there">
        {#each trip.options as option, index (index)}
          <button
            class="option"
            class:chosen={index === trip.chosen}
            aria-pressed={index === trip.chosen}
            onclick={() => choose(index)}
          >
            <span class="option-time">{duration(option.time)}</span>
            <span class="option-distance">{distance(option.distance)}</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if route}
      <div class="summary">
        <span class="figure">{duration(route.time)}</span>
        <span class="detail">
          {distance(route.distance)} · Arrival {arrival}
        </span>
      </div>
    {/if}

    {#if trip.planning}
      <p class="status">
        <Spinner size={16} label="Finding a route" />
        Finding a route…
      </p>
    {:else if trip.error}
      <div class="problem">
        <p class="status warning">{trip.error}</p>
        <div class="problem-actions">
          <button class="quiet" onclick={() => retry()}>
            <Icon name="refresh" size={16} />
            Try again
          </button>
          <!-- Back to what was there: the route before the change, or
               with none yet, just the pin. -->
          <button class="quiet" onclick={dismiss}>Cancel</button>
        </div>
      </div>
    {/if}

    {#if trip.destination}
      <button class="start" disabled={trip.planning} onclick={onstart}>
        <Icon name="play" size={18} />
        Start
      </button>
    {/if}
  </section>
{/if}

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--spacing);
    width: 340px;
    padding: var(--spacing);
    background: color-mix(in srgb, var(--surface) 96%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.3);
  }

  header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: start;
    gap: var(--spacing-s);
  }

  .mark {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    color: var(--accent-ink);
    background: var(--accent);
    border-radius: var(--radius-sm);
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .eyebrow {
    font-size: 10px;
  }

  .title {
    overflow: hidden;
    font-size: 18px;
    font-weight: 600;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .subtitle {
    overflow: hidden;
    font-size: 14px;
    color: var(--text-dim);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .stops {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .stops li {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--spacing-s);
    min-height: 40px;
    padding-left: 6px;
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .number {
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 700;
    color: var(--accent-ink);
    background: var(--accent);
    border-radius: 50%;
  }

  .stop-name {
    overflow: hidden;
    font-size: 14px;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .remove {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .options {
    display: grid;
    grid-auto-columns: 1fr;
    grid-auto-flow: column;
    gap: var(--spacing-xs);
  }

  .option {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
    min-height: 48px;
    padding: 4px;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .option.chosen {
    color: var(--accent);
    background: var(--accent-soft);
    border-color: var(--accent);
  }

  .option-time {
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
  }

  .option-distance {
    font-size: 12px;
    color: var(--text-dim);
  }

  .summary {
    display: flex;
    align-items: baseline;
    gap: var(--spacing-s);
  }

  .figure {
    font-family: var(--font-display);
    font-size: 26px;
    font-weight: 700;
    line-height: 1;
  }

  .detail {
    font-size: 14px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .status {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    margin: 0;
    font-size: 14px;
    color: var(--text-dim);
  }

  .warning {
    color: var(--danger);
  }

  .problem {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
  }

  .problem-actions {
    display: flex;
    gap: var(--spacing-s);
  }

  .quiet {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 40px;
    padding: 0 var(--spacing);
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .start {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-s);
    height: 48px;
    padding: 0 var(--spacing);
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    border-radius: var(--radius-sm);
    color: var(--accent-ink);
    background: var(--accent);
    border: 0;
  }

  .start:disabled {
    opacity: 0.5;
  }

  /* Round, as tall as the mark beside the title. */
  .end {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    color: var(--text-dim);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  button:active:not(:disabled) {
    filter: brightness(0.92);
  }
</style>
