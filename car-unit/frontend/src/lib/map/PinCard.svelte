<script lang="ts">
  import Icon from '../Icon.svelte'
  import Keyboard from '../ui/Keyboard.svelte'
  import Spinner from '../ui/Spinner.svelte'
  import * as places from '../api/places'
  import { metresBetween } from '../address'
  import type { Place } from '../api/types'
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

  /* Saving the pin as a place: the star in the header, a name typed
     on the keyboard, and the daemon's places -- the ones the search
     list, the weather and Settings all read. */

  /** Closer than this to a saved place, the pin is on it. */
  const SAME_METRES = 30

  let savedPlaces = $state<Place[]>([])
  $effect(() => {
    places
      .saved()
      .then((list) => (savedPlaces = list))
      .catch(() => {})
  })

  /** The saved place the pin is on, if any. */
  const savedAs = $derived(
    savedPlaces.find(
      (place) =>
        metresBetween(
          place.latitude,
          place.longitude,
          pin.latitude,
          pin.longitude,
        ) < SAME_METRES,
    )?.name ?? null,
  )

  let naming = $state(false)
  let saving = $state(false)
  let saveError = $state('')
  /** A typed name already used by a place somewhere else: saving
   *  under it moves that place here, so it is asked first. */
  let clash = $state<{ name: string; typed: string } | null>(null)

  async function store(name: string): Promise<void> {
    clash = null
    saving = true
    saveError = ''
    try {
      savedPlaces = await places.save({
        name,
        latitude: pin.latitude,
        longitude: pin.longitude,
        address: [pin.title, pin.subtitle].filter(Boolean).join(', '),
        lookup: !pin.title,
      })
    } catch {
      saveError = 'Could not save the place.'
    } finally {
      saving = false
    }
  }

  function named(text: string): void {
    naming = false
    const name = text.trim()
    if (!name) return
    const existing = savedPlaces.find(
      (place) => place.name.toLowerCase() === name.toLowerCase(),
    )
    if (existing) {
      clash = { name: existing.name, typed: name }
      return
    }
    store(name)
  }

  const capital = (text: string) =>
    text ? text[0].toUpperCase() + text.slice(1) : text
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

    <div class="corner">
      <!-- Filled when the pin is on a saved place, and then only says
           so: renaming or forgetting one is done in Settings. -->
      <button
        class="icon"
        class:on={!!savedAs}
        aria-label={savedAs ? `Saved as ${capital(savedAs)}` : 'Save this place'}
        disabled={pin.looking || saving || !!savedAs}
        onclick={() => (naming = true)}
      >
        {#if saving}
          <Spinner size={18} label="Saving" />
        {:else}
          <Icon name={savedAs ? 'star-filled' : 'star'} size={20} />
        {/if}
      </button>
      <button class="icon" aria-label="Remove the pin" onclick={onclose}>
        <Icon name="close" size={18} />
      </button>
    </div>
  </header>

  {#if savedAs}
    <p class="note saved">
      <Icon name="star-filled" size={14} />
      Saved as {capital(savedAs)}
    </p>
  {:else if clash}
    <div class="clash">
      <p class="note">
        “{capital(clash.name)}” is already saved somewhere else. Move it
        here?
      </p>
      <div class="clash-actions">
        <button class="secondary" onclick={() => clash && store(clash.typed)}>
          Move here
        </button>
        <button class="secondary" onclick={() => (clash = null)}>Cancel</button>
      </div>
    </div>
  {:else if saveError}
    <p class="note warning">{saveError}</p>
  {/if}

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

{#if naming}
  <!-- The keyboard's own buffer above the keys, with the address as
       a start: most places are saved under a short name of their
       own, and the street is something to edit down from. -->
  <Keyboard
    initial={pin.title}
    label="Name the place"
    placeholder="Home, work…"
    maxlength={32}
    ondone={named}
    oncancel={() => (naming = false)}
  />
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

  .corner {
    display: flex;
    margin: -4px -4px 0 0;
  }

  .icon {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .icon:active:not(:disabled) {
    background: var(--panel-2);
  }

  /* Saved: the star in the accent, as the saved places are in the
     search list. Disabled, but not dimmed -- it is saying something. */
  .icon.on {
    color: var(--accent);
  }

  .icon:disabled:not(.on) {
    opacity: 0.45;
  }

  .note {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    font-size: 13.5px;
    color: var(--text-dim);
  }

  .note.saved :global(svg) {
    color: var(--accent);
  }

  .note.warning {
    color: var(--danger);
  }

  .clash {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
  }

  .clash-actions {
    display: flex;
    gap: var(--spacing-s);
  }

  .clash-actions .secondary {
    flex: 1;
    height: 40px;
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

  .icon:focus-visible,
  .secondary:focus-visible,
  .directions:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
