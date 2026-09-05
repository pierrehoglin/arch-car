<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Keyboard from '$lib/ui/Keyboard.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import { MIN_CHARS, suggest } from '$lib/api/places'
  import type { Address } from '$lib/api/types'

  /* The map itself is not here yet. This is the chrome that sits over
     it -- search, speed, and the controls -- so the layout is settled
     before MapLibre and the pmtiles archive are wired in. */

  /** Long enough that the list is not rebuilt mid-word, short enough
   *  that it still feels like it follows the typing. */
  const DEBOUNCE_MS = 220

  let field = $state<HTMLInputElement>()
  let query = $state('')
  let typing = $state(false)

  let results = $state<Address[]>([])
  let searching = $state(false)
  let chosen = $state<Address | null>(null)

  const speed = 40

  /* Debounced, and the result of a stale request is thrown away.
     Without the second part a slow reply for "kun" can land after a
     quick one for "kungsgatan" and replace it. */
  let sequence = 0

  $effect(() => {
    const text = query.trim()

    if (text.length < MIN_CHARS) {
      results = []
      searching = false
      return
    }

    const ticket = ++sequence
    searching = true

    const timer = setTimeout(async () => {
      try {
        const found = await suggest(text)
        if (ticket === sequence) results = found
      } catch {
        if (ticket === sequence) results = []
      } finally {
        if (ticket === sequence) searching = false
      }
    }, DEBOUNCE_MS)

    return () => clearTimeout(timer)
  })

  function choose(place: Address): void {
    chosen = place
    query = place.display_name
    results = []
    typing = false
  }

  /** The line worth reading first: a name, or the street. */
  function title(place: Address): string {
    if (place.name) return place.name
    return [place.road, place.house_number].filter(Boolean).join(' ')
  }

  /** Everything after it, minus what the title already said. */
  function detail(place: Address): string {
    return place.display_name
      .split(', ')
      .filter((part) => part !== title(place))
      .join(', ')
  }
</script>

<div class="map">
  <div class="surface" aria-hidden="true">
    <p class="pending">Map</p>
  </div>

  <div class="search">
    <div class="query">
      <Icon name="search" size={20} />

      <!-- Editable, not readonly: browsers will not place a caret in
           a readonly field on a touch screen, and the caret is the
           whole point of it being a real input. inputmode="none"
           keeps the caret while telling the browser not to raise a
           keyboard of its own. -->
      <input
        bind:this={field}
        bind:value={query}
        type="text"
        inputmode="none"
        placeholder="Search places..."
        aria-label="Search places"
        autocomplete="off"
        spellcheck="false"
        onclick={() => (typing = true)}
      />

      {#if searching}
        <Spinner size={18} label="Searching" />
      {:else if query}
        <button
          class="clear"
          aria-label="Clear"
          onclick={() => {
            query = ''
            chosen = null
            field?.focus()
          }}
        >
          <Icon name="close" size={18} />
        </button>
      {/if}
    </div>

    <button class="go" disabled={!chosen}>Go</button>

    {#if results.length}
      <ul class="results">
        {#each results as place (place.osm_id)}
          <li>
            <button class="result" onclick={() => choose(place)}>
              <span class="result-title">{title(place)}</span>
              <span class="result-detail">{detail(place)}</span>
            </button>
          </li>
        {/each}
      </ul>
    {:else if query.trim().length >= MIN_CHARS && !searching}
      <p class="empty">Nothing found</p>
    {/if}
  </div>

  <div class="speed">
    <span class="figure">{speed}</span>
    <span class="unit">km/h</span>
  </div>

  <div class="controls">
    <button class="control primary" aria-label="Centre on position">
      <Icon name="crosshair" size={22} />
    </button>
    <button class="control" aria-label="Reset bearing">
      <Icon name="compass" size={22} />
    </button>
    <button class="control" aria-label="Zoom out">
      <Icon name="remove" size={22} />
    </button>
  </div>

  <p class="attribution">© OpenStreetMap contributors</p>

  <!-- Live, so suggestions can follow the typing. The field stays
       visible above the sheet, which is what makes that worth doing;
       for a field the keyboard covers, the buffer is the better
       shape. -->
  <!-- Given the field itself, so edits land at the caret rather than
       on the end of a string -- which is what makes the arrow keys
       mean anything.
       
       No onchange: the keyboard dispatches a real input event, so
       bind:value above already hears every edit. Taking the value
       through a callback as well would be two paths to the same
       state, and they would disagree the moment one of them was
       changed. -->
  {#if typing}
    <Keyboard
      initial={query}
      label="Search places"
      target={field}
      maxlength={64}
      ondone={() => (typing = false)}
      oncancel={() => (typing = false)}
    />
  {/if}
</div>

<style>
  .map {
    position: relative;
    height: 100%;
    overflow: hidden;
  }

  /* Stand-in for the map canvas. Deliberately plain -- a fake street
     grid would only be mistaken for the real thing in a screenshot. */
  .surface {
    display: grid;
    place-items: center;
    height: 100%;
    background: var(--panel-2);
  }

  .pending {
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  /* Everything below floats over the map, so each piece carries its
     own background rather than relying on the surface behind it. */
  .search {
    position: absolute;
    top: 18px;
    left: 18px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .query {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    width: 380px;
    height: 46px;
    padding: 0 var(--spacing);
    color: var(--text-dim);
    background: color-mix(in srgb, var(--bar) 94%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .query:focus-within {
    border-color: var(--accent);
  }

  .query input {
    flex: 1;
    min-width: 0;
    padding: 0;
    font-family: var(--font-body);
    font-size: 16px;
    color: var(--text);
    background: none;
    border: 0;
    caret-color: var(--accent);
  }

  .query input::placeholder {
    color: var(--text-faint);
  }

  .query input:focus {
    outline: none;
  }

  .clear {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  /* Under the field, over the map. Capped so a long list does not
     reach the keyboard, which occupies the lower half of the screen
     while this is being typed into. */
  .results {
    position: absolute;
    top: 54px;
    left: 0;
    width: 380px;
    max-height: 300px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .result {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    min-height: 62px;
    padding: var(--spacing-s) var(--spacing);
    text-align: left;
    background: none;
    border: 0;
    border-bottom: 1px solid var(--hairline);
  }

  li:last-child .result {
    border-bottom: 0;
  }

  .result:active {
    background: var(--panel-2);
  }

  .result:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .result-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  .result-detail {
    font-size: 12.5px;
    color: var(--text-dim);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .empty {
    position: absolute;
    top: 54px;
    left: 0;
    width: 380px;
    margin: 0;
    padding: var(--spacing);
    font-size: 14px;
    color: var(--text-faint);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .go {
    height: 46px;
    padding: 0 22px;
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--accent-ink);
    background: var(--accent);
    border: 0;
    border-radius: var(--radius-sm);
  }

  .go:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .speed {
    position: absolute;
    top: 18px;
    right: 22px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1;
  }

  .figure {
    font-family: var(--font-display);
    font-size: 34px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    /* Full brightness even under Night Panel: this is the readout the
       mode exists to keep legible. */
    color: var(--text);
  }

  .unit {
    margin-top: 2px;
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  .controls {
    position: absolute;
    right: 22px;
    bottom: 28px;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
  }

  .control {
    display: grid;
    place-items: center;
    width: 54px;
    height: 54px;
    color: var(--text);
    background: color-mix(in srgb, var(--bar) 88%, transparent);
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  /* Recentring is the one control pressed while driving, so it is
     the only one that carries the accent. */
  .control.primary {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: transparent;
  }

  .control:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Required by the ODbL licence the map data is under. */
  .attribution {
    position: absolute;
    right: 10px;
    bottom: 6px;
    margin: 0;
    font-size: 11px;
    color: var(--text-faint);
  }
</style>
