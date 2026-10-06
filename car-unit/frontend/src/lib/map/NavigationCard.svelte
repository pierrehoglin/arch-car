<script lang="ts">
  import Icon from '../Icon.svelte'
  import Spinner from '../ui/Spinner.svelte'
  import { turnDistance, turnIcon } from './turnIcons'
  import { dismissError, end, nav, removeStop } from '../navigation.svelte'

  /* The route while it is being driven: where to, what is left, and
     the turns ahead. Takes the route card's place in the bottom-left
     column once navigation starts, and grows upwards like it.

     The next two turns by default; all of them on request, scrolling
     inside the card so it never covers more than the lower part of the
     map. Which of the two is remembered with the session. */

  const session = $derived(nav.session)
  const arrived = $derived(session?.state === 'arrived')
  const steps = $derived(session?.steps ?? [])
  const shown = $derived(nav.showAll ? steps : steps.slice(0, 2))

  /* Arrival moves with the clock even while the car is stopped. */
  let now = $state(Date.now())
  $effect(() => {
    const timer = setInterval(() => (now = Date.now()), 30_000)
    return () => clearInterval(timer)
  })

  const arrival = $derived(
    session?.remaining_time !== undefined
      ? new Date(now + session.remaining_time * 1000).toLocaleTimeString(
          'sv-SE',
          { hour: '2-digit', minute: '2-digit' },
        )
      : '',
  )

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

  const heading = $derived(
    arrived
      ? 'Arrived at'
      : session?.state === 'resuming'
        ? 'Resuming route to'
        : 'Navigating to',
  )
</script>

{#if session && session.state !== 'idle'}
  <section class="card" aria-label="Navigation">
    <header>
      <span class="mark">
        <Icon name={arrived ? 'flag' : 'directions'} size={20} />
      </span>
      <div class="what">
        <span class="eyebrow">{heading}</span>
        <span class="title">{session.destination?.title ?? ''}</span>
        {#if session.destination?.subtitle}
          <span class="subtitle">{session.destination.subtitle}</span>
        {/if}
      </div>
      <!-- Ending, small and out of the way in the corner: pressed once
           a drive, and the card has more use for the room. -->
      {#if !arrived}
        <button class="end" aria-label="End route" onclick={() => end()}>
          <Icon name="trash" size={20} />
        </button>
      {/if}
    </header>

    {#if !arrived}
      <div class="summary">
        <span class="figure">{duration(session.remaining_time ?? 0)}</span>
        <span class="detail">
          {distance(session.remaining ?? 0)} · Arrival {arrival}
        </span>
      </div>

      {#if shown.length}
        <ol
          class="steps"
          class:all={nav.showAll}
          class:stale={session.on_route === false}
        >
          {#each shown as step, index (`${index}:${step.kind}:${step.instruction}`)}
            <li class:next={index === 0}>
              {#if step.stop}
                <span class="number">{step.stop}</span>
              {:else}
                <span class="turn">
                  <Icon name={turnIcon(step.kind)} size={20} />
                </span>
              {/if}
              <span class="step-text">
                {step.stop
                  ? `Stop ${step.stop}: ${step.title || step.instruction}`
                  : step.instruction}
              </span>
              <span class="step-distance">
                {step.distance < 20 ? 'Now' : `in ${turnDistance(step.distance)}`}
              </span>
              {#if step.stop}
                <button
                  class="remove"
                  aria-label="Remove stop {step.stop}"
                  disabled={nav.busy}
                  onclick={() => removeStop((step.stop ?? 1) - 1)}
                >
                  <Icon name="close" size={16} />
                </button>
              {/if}
            </li>
          {/each}
        </ol>

        {#if steps.length > 2}
          <button class="toggle" onclick={() => (nav.showAll = !nav.showAll)}>
            {nav.showAll ? 'Show fewer' : `Show all steps (${steps.length})`}
          </button>
        {/if}
      {/if}
    {/if}

    {#if nav.busy}
      <p class="status">
        <Spinner size={16} label="Changing the route" />
        Changing the route…
      </p>
    {:else if nav.error}
      <div class="problem">
        <p class="status warning">{nav.error}</p>
        <button class="quiet" onclick={dismissError}>OK</button>
      </div>
    {/if}

    {#if arrived}
      <button class="done" onclick={() => end()}>Done</button>
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

  .steps {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* All of them: scrolls inside the card rather than growing it past
     the lower part of the map. */
  .steps.all {
    max-height: 280px;
    overflow-y: auto;
  }

  /* Off the route: the turns are the old route's until a new one
     comes, and their distances are measured from the nearest point of
     it rather than from the car. */
  .steps.stale {
    opacity: 0.5;
  }

  .steps li {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto auto;
    align-items: center;
    gap: var(--spacing-s);
    min-height: 44px;
    padding: 4px 6px;
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .steps li.next {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .turn {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    color: var(--text);
  }

  .next .turn {
    color: var(--accent);
  }

  .number {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    margin: 0 2px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 700;
    color: var(--accent-ink);
    background: var(--accent);
    border-radius: 50%;
  }

  .step-text {
    display: -webkit-box;
    overflow: hidden;
    font-size: 14px;
    line-height: 1.3;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .step-distance {
    font-size: 13px;
    color: var(--text-dim);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .remove {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .toggle {
    align-self: flex-start;
    height: 36px;
    padding: 0 var(--spacing-s);
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    background: none;
    border: 0;
    border-radius: var(--radius-sm);
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
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing-s);
  }

  .quiet {
    height: 36px;
    padding: 0 var(--spacing);
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  /* Round, in the header's corner, as tall as the mark beside the
     title so the header does not grow for it. */
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

  .done {
    height: 48px;
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--accent-ink);
    background: var(--accent);
    border: 0;
    border-radius: var(--radius-sm);
  }

  button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  button:active:not(:disabled) {
    filter: brightness(0.92);
  }
</style>
