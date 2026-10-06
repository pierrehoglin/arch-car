<script lang="ts">
  import Icon from '../Icon.svelte'
  import Spinner from '../ui/Spinner.svelte'
  import type { Pin } from '../destination.svelte'

  /* What the pin is on. Bottom left of the map, growing upwards as it
     gains more to say -- it is anchored at its foot, so anything added
     above the buttons pushes the top up rather than the buttons down
     off the screen. */

  interface Props {
    pin: Pin
    /** "2.3 km away", from the car. Absent with no position. */
    distance?: string
    /** A route exists: the pin can replace its destination or join it
     *  as a stop, rather than start a route of its own. */
    routing?: boolean
    /** A route is being worked out; asking for another would only
     *  replace that request. */
    busy?: boolean
    ondirections: () => void
    onsetdestination: () => void
    onaddstop: () => void
    onclose: () => void
  }

  let {
    pin,
    distance = '',
    routing = false,
    busy = false,
    ondirections,
    onsetdestination,
    onaddstop,
    onclose,
  }: Props = $props()

  /* A point still being looked up has nothing to name it by yet. */
  const blocked = $derived(busy || pin.looking)
</script>

<section class="card" aria-label="Pin">
  <header>
    <span class="mark">
      <Icon name="pin" size={20} />
    </span>

    <div class="what">
      {#if pin.looking}
        <span class="title pending">
          <Spinner size={16} label="Looking up the address" />
          Looking up address…
        </span>
      {:else}
        <span class="title">{pin.title}</span>
        {#if pin.subtitle}
          <span class="subtitle">{pin.subtitle}</span>
        {/if}
      {/if}
      {#if distance}
        <span class="distance">{distance}</span>
      {/if}
    </div>

    <button class="close" aria-label="Remove the pin" onclick={onclose}>
      <Icon name="close" size={18} />
    </button>
  </header>

  <!-- Room for more about the place goes here, above the actions. -->

  <div class="actions">
    {#if routing}
      <button
        class="directions"
        disabled={blocked}
        onclick={onsetdestination}
      >
        <Icon name="directions" size={20} />
        Set as destination
      </button>
      <button class="secondary" disabled={blocked} onclick={onaddstop}>
        <Icon name="add" size={20} />
        Add stop
      </button>
    {:else}
      <button class="directions" disabled={blocked} onclick={ondirections}>
        {#if busy}
          <Spinner size={18} label="Finding a route" />
          Finding a route…
        {:else}
          <Icon name="directions" size={20} />
          Directions
        {/if}
      </button>
    {/if}
  </div>
</section>

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
    padding-top: 2px;
  }

  .title {
    overflow: hidden;
    font-size: 18px;
    font-weight: 600;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .title.pending {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    font-size: 15px;
    font-weight: 400;
    color: var(--text-dim);
  }

  .subtitle {
    overflow: hidden;
    font-size: 14px;
    color: var(--text-dim);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .distance {
    font-size: 12.5px;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .close {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    margin: -4px -4px 0 0;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .close:active {
    background: var(--panel-2);
  }

  .actions {
    display: flex;
    gap: var(--spacing-s);
  }

  .directions {
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-s);
    height: 48px;
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--accent-ink);
    background: var(--accent);
    border: 0;
    border-radius: var(--radius-sm);
  }

  .directions:active,
  .secondary:active {
    filter: brightness(0.92);
  }

  .secondary {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-xs);
    height: 48px;
    padding: 0 var(--spacing);
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .directions:disabled,
  .secondary:disabled {
    opacity: 0.55;
  }

  .close:focus-visible,
  .secondary:focus-visible,
  .directions:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
