<script lang="ts">
  import Icon from '../Icon.svelte'
  import Spinner from '../ui/Spinner.svelte'
  import { turnDistance, turnIcon } from './turnIcons'
  import type { NavState } from '../api/navigation'

  /* The next turn, as large as it can be read at a glance: the arrow,
     how far, and what to do. Where the search field is when not
     navigating -- the top left, the first place the eye goes.

     When the route is not being followed -- rerouting, off it with no
     way back yet, waiting for GPS after a restart -- the banner says
     that instead, since the turn it would show may not be the one. */

  interface Props {
    session: NavState
    /** Smaller, filling the width it is given: the home screen's map
     *  tile, where it shares the top with the speed. */
    compact?: boolean
  }

  let { session, compact = false }: Props = $props()

  /* The arrow's size, and the spinner's, in each of the two sizes. */
  const big = $derived(compact ? 32 : 44)
  const middle = $derived(compact ? 26 : 36)

  const next = $derived(session.next)
  const then = $derived(session.then)
  const waiting = $derived(
    session.state === 'rerouting' || session.state === 'resuming',
  )
</script>

<section
  class="banner"
  class:compact
  aria-live="polite"
  aria-label="Next instruction"
>
  {#if session.state === 'arrived'}
    <span class="arrow">
      <Icon name="flag" size={middle + 4} />
    </span>
    <div class="words">
      <span class="distance">You have arrived</span>
      <span class="instruction">{session.destination?.title ?? ''}</span>
    </div>
  {:else if waiting || session.state === 'offline'}
    <span class="arrow quiet">
      {#if waiting}
        <Spinner size={compact ? 24 : 32} label={session.message ?? ''} />
      {:else}
        <Icon name="directions" size={middle} />
      {/if}
    </span>
    <div class="words">
      <span class="instruction status" class:warning={session.state === 'offline'}>
        {session.message}
      </span>
    </div>
  {:else if next}
    <span class="arrow">
      <Icon name={next.stop ? 'flag' : turnIcon(next.kind)} size={big} />
    </span>
    <div class="words">
      <span class="distance">{turnDistance(next.distance)}</span>
      <span class="instruction">
        {next.stop ? `Stop ${next.stop}: ${next.title || next.instruction}` : next.instruction}
      </span>
      {#if then}
        <span class="then">
          Then
          <Icon name={then.stop ? 'flag' : turnIcon(then.kind)} size={16} />
          {then.stop
            ? `Stop ${then.stop}: ${then.title || then.instruction}`
            : then.street || then.instruction}
        </span>
      {/if}
    </div>
  {/if}
</section>

<style>
  .banner {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: var(--spacing);
    width: 440px;
    min-height: 92px;
    padding: var(--spacing-s);
    background: color-mix(in srgb, var(--surface) 97%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.3);
  }

  /* The arrow on the accent, the one thing on the screen that should
     be found without looking for it. */
  .arrow {
    display: grid;
    place-items: center;
    width: 76px;
    height: 76px;
    color: var(--accent-ink);
    background: var(--accent);
    border-radius: var(--radius-sm);
  }

  .arrow.quiet {
    color: var(--text-dim);
    background: var(--panel-2);
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .distance {
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 700;
    line-height: 1.05;
    font-variant-numeric: tabular-nums;
  }

  /* Two lines at most: a long street name is cut rather than pushing
     the banner down over the map. */
  .instruction {
    display: -webkit-box;
    overflow: hidden;
    font-size: 16px;
    font-weight: 600;
    line-height: 1.3;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .instruction.status {
    font-weight: 500;
    color: var(--text-dim);
  }

  .instruction.warning {
    color: var(--danger);
  }

  /* The home tile's: the same parts, a size down. */
  .banner.compact {
    width: 100%;
    min-height: 0;
    gap: var(--spacing-s);
    padding: 6px;
  }

  .compact .arrow {
    width: 54px;
    height: 54px;
  }

  .compact .distance {
    font-size: 22px;
  }

  .compact .instruction {
    font-size: 14px;
  }

  .compact .then {
    font-size: 12px;
  }

  .then {
    display: flex;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    font-size: 13px;
    color: var(--text-dim);
    white-space: nowrap;
    text-overflow: ellipsis;
  }
</style>
