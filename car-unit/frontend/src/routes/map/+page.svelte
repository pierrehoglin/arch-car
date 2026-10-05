<script lang="ts">
  import { untrack } from 'svelte'
  import { Map as MapLibre } from 'maplibre-gl'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import Icon from '$lib/Icon.svelte'
  import Keyboard from '$lib/ui/Keyboard.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import { MIN_CHARS, suggest } from '$lib/api/places'
  import * as mapApi from '$lib/api/map'
  import { RequestFailed } from '$lib/api/client'
  import { mapStyle, registerProtocol } from '$lib/map/style'
  import { isDark } from '$lib/settings.svelte'
  import type { Address } from '$lib/api/types'

  /* The map: pan, zoom and rotate, never tilted. Opens north up; a
     compass appears once it has been turned, and turns it back. The
     chrome over it -- search, speed, controls -- was laid out first
     and stays as it was. */

  /** Where the map opens, until there is a GPS position to open on. */
  const START = {
    center: [18.0686, 59.3293] as [number, number],
    zoom: 12,
    bearing: 0,
  }

  /** Degrees off north before the compass is worth showing. MapLibre
   *  snaps anything inside 7 back to north at the end of a twist, so
   *  a smaller angle never stays on screen anyway. */
  const TURNED = 0.5

  /** How far past the archive's edge panning may go, in degrees. A
   *  little slack so a border town is not pinned to the screen edge;
   *  not so much that the map can be lost in empty background. */
  const BOUNDS_SLACK = 1.5

  let container = $state<HTMLDivElement>()

  /* Plain, not $state: MapLibre owns its own state, and proxying the
     instance would wrap every internal object it touches. */
  let map: MapLibre | undefined

  /** Which flavour the map was last given. Plain, like the map. */
  let flavour: boolean | null = null

  /** Whether the daemon has the label fonts and icons, as it said
   *  when the map was built. Downloaded later, they are picked up the
   *  next time the screen opens. */
  let localLabels = false

  /** Set once the style has loaded, so the theme effect below knows
   *  there is something to restyle. */
  let ready = $state(false)

  /** Which way the map faces, in degrees clockwise from north.
   *  Mirrored from MapLibre, for the compass. */
  let bearing = $state(0)

  /** Why there is no map, when there is not. */
  let problem = $state<{ title: string; detail: string } | null>(null)

  /* Built once, when the container exists. untrack around the theme,
     so switching Day/Night restyles the map rather than tearing it
     down and building another -- that is the next effect's job. */
  $effect(() => {
    const element = container
    if (!element) return

    let cancelled = false
    let created: MapLibre | undefined

    mapApi
      .status()
      .then((info) => {
        if (cancelled) return

        if (!info.available) {
          problem = { title: 'No map installed', detail: info.hint }
          return
        }

        registerProtocol()
        const [west, south, east, north] = info.bounds
        const dark = untrack(isDark)
        flavour = dark
        localLabels = info.labels.available

        created = new MapLibre({
          container: element,
          style: mapStyle(dark, localLabels),
          center: START.center,
          zoom: START.zoom,
          minZoom: 4,
          /* The archive stops at 15; beyond it MapLibre stretches the
             last level, which stays sharp because it is vectors. */
          maxZoom: 18,
          maxBounds: [
            [west - BOUNDS_SLACK, south - BOUNDS_SLACK],
            [east + BOUNDS_SLACK, north + BOUNDS_SLACK],
          ],
          /* Rotation yes -- two fingers twisting, or right-drag and
             Ctrl-drag with a mouse. Tilt no: a flat map reads at a
             glance, and a tilt picked up by accident while rotating
             is hard to undo on a touch screen. */
          pitchWithRotate: false,
          touchPitch: false,
          maxPitch: 0,
          /* Shown in our own corner instead, in the panel's type. */
          attributionControl: false,
        })
        created.on('rotate', () => {
          bearing = created?.getBearing() ?? 0
        })

        created.on('load', () => {
          if (!cancelled) ready = true
        })
        created.on('error', (event) => {
          const message = event.error?.message ?? String(event)
          console.warn('map:', message)

          /* Said on screen when it stops the map from appearing at
             all -- a grey panel with the reason in the console is no
             help on a car's screen. Not for failures from elsewhere:
             the label fonts and icons still come from the internet,
             and losing them without signal should leave a map with
             no names, not a message instead of the map. */
          const url = (event.error as { url?: string } | undefined)?.url ?? ''
          const elsewhere =
            /^https?:/.test(url) && !url.startsWith(location.origin)
          if (!ready && !cancelled && !elsewhere) {
            problem = { title: 'The map did not load', detail: message }
          }
        })

        map = created
      })
      .catch((cause) => {
        if (cancelled) return
        /* Two different failures land here: the daemon not answering
           the status call, and MapLibre refusing to start -- most
           often because the browser has no WebGL. Saying "is carlibd
           running?" for the second would send you to the wrong
           place. */
        problem =
          cause instanceof RequestFailed
            ? {
                title: 'Map unavailable',
                detail: 'The car service did not answer. Is carlibd running?',
              }
            : {
                title: 'The map could not start',
                detail: cause instanceof Error ? cause.message : String(cause),
              }
        console.warn('map:', cause)
      })

    return () => {
      cancelled = true
      ready = false
      flavour = null
      created?.remove()
      map = undefined
    }
  })

  /* Day and Night. The flavour is a different set of paint values on
     the same layers, so MapLibre diffs it in place -- no flash, and
     the tiles already loaded are kept. */
  $effect(() => {
    const dark = isDark()
    if (!ready || !map || dark === flavour) return
    flavour = dark
    map.setStyle(mapStyle(dark, localLabels))
  })

  const zoomIn = () => map?.zoomIn()
  const zoomOut = () => map?.zoomOut()
  const backToStart = () => map?.easeTo({ ...START, duration: 600 })
  const faceNorth = () => map?.easeTo({ bearing: 0, duration: 400 })

  const turned = $derived(Math.abs(bearing) > TURNED)

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
  <div class="canvas" bind:this={container}></div>

  {#if problem}
    <div class="surface">
      <p class="pending">{problem.title}</p>
      <p class="help">{problem.detail}</p>
    </div>
  {/if}

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
    <!-- Only while the map is turned. At the top of a column anchored
         to the bottom, so the buttons below it do not move when it
         comes and goes. The needle points where north is. -->
    {#if turned}
      <button
        class="control compass"
        aria-label="Face north"
        disabled={!ready}
        onclick={faceNorth}
      >
        <svg
          viewBox="0 0 24 24"
          width="26"
          height="26"
          aria-hidden="true"
          style:transform="rotate({-bearing}deg)"
        >
          <path class="north" d="M12 2 L16 12 L8 12 Z" />
          <path class="south" d="M12 22 L8 12 L16 12 Z" />
        </svg>
      </button>
    {/if}
    <!-- Back to where the map opened, for now. Becomes "centre on
         the car" once there is a position. -->
    <button
      class="control primary"
      aria-label="Back to start"
      disabled={!ready}
      onclick={backToStart}
    >
      <Icon name="crosshair" size={22} />
    </button>
    <button
      class="control"
      aria-label="Zoom in"
      disabled={!ready}
      onclick={zoomIn}
    >
      <Icon name="add" size={22} />
    </button>
    <button
      class="control"
      aria-label="Zoom out"
      disabled={!ready}
      onclick={zoomOut}
    >
      <Icon name="remove" size={22} />
    </button>
  </div>

  <p class="attribution">© Protomaps · © OpenStreetMap contributors</p>

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

  /* MapLibre fills this and draws into a canvas of its own. The
     panel colour shows until the first tiles arrive. */
  .canvas {
    position: absolute;
    inset: 0;
    background: var(--panel-2);
  }

  /* Said in place of the map when there is none. Over the canvas, so
     the search and controls still sit on top of it. */
  .surface {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-s);
    padding: 0 15%;
    text-align: center;
    background: var(--panel-2);
  }

  .help {
    max-width: 60ch;
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-dim);
    user-select: text;
    word-break: break-word;
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

  /* The north half in the accent, so which end is which reads
     without a letter on it. */
  .compass .north {
    fill: var(--accent);
  }

  .compass .south {
    fill: var(--text-dim);
  }

  .control:disabled {
    opacity: 0.4;
    cursor: default;
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
