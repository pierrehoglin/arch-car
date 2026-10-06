<script lang="ts">
  import { untrack } from 'svelte'
  import { Map as MapLibre, Marker } from 'maplibre-gl'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import Icon from '$lib/Icon.svelte'
  import Keyboard from '$lib/ui/Keyboard.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import { MIN_CHARS, saved, suggest } from '$lib/api/places'
  import * as mapApi from '$lib/api/map'
  import { RequestFailed } from '$lib/api/client'
  import { mapStyle, registerProtocol } from '$lib/map/style'
  import { isDark } from '$lib/settings.svelte'
  import CarMarker from '$lib/map/CarMarker.svelte'
  import DestinationPin from '$lib/map/DestinationPin.svelte'
  import PinCard from '$lib/map/PinCard.svelte'
  import RouteCard from '$lib/map/RouteCard.svelte'
  import { ALTERNATIVES, boundsOf, drawRoutes } from '$lib/map/routeLines'
  import { TripMarkers } from '$lib/map/tripMarkers'
  import {
    addStop,
    choose as chooseOption,
    hasRoute,
    planTo,
    setDestination,
    trip,
  } from '$lib/route.svelte'
  import { Car, type CarLook } from '$lib/map/car'
  import { distanceLabel, metresBetween } from '$lib/address'
  import {
    clear as clearPin,
    destination,
    dropAt,
    fromSaved,
    fromSearch,
  } from '$lib/destination.svelte'
  import {
    located,
    position,
    refresh as refreshPosition,
    speedOf,
    watch as watchPosition,
  } from '$lib/position.svelte'
  import type { Address, Place } from '$lib/api/types'

  /* The map: pan, zoom and rotate, never tilted. Opens north up; a
     compass appears once it has been turned, and turns it back. The
     chrome over it -- search, speed, controls -- was laid out first
     and stays as it was. */

  /** Where the map opens when nothing at all is known about where
   *  the car is -- no fix, nothing remembered, no pin. */
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

  /** Zoom for the car's surroundings: streets with their names. */
  const NEAR = 15

  /** Zoom for a chosen place: close enough to see which building. */
  const PIN_ZOOM = 16

  /** The pin's marker element, drawn by DestinationPin, and the
   *  MapLibre marker carrying it. Plain, like the map. */
  let pinElement = $state<HTMLDivElement>()
  let pinMarker: Marker | undefined
  let pinShown = false

  /** The route's destination flag and numbered stops. Plain. */
  let tripMarkers: TripMarkers | undefined

  /** The plan last fitted on screen. Starts at the current one, so
   *  coming back to the screen with a route keeps the map on the car
   *  rather than zooming out again; a new plan is fitted once. */
  let fitted = trip.version

  /** The car's marker element, drawn by CarMarker; and what moves
   *  it, once there is a map. Plain, like the map. */
  let carElement = $state<HTMLDivElement>()
  let car: Car | undefined
  let look = $state<CarLook>({ source: 'none', pointing: false })

  /** Keeping the car in the middle of the screen. Starts on when
   *  the map opens on the car; dragging the map turns it off, and
   *  the locate button turns it back on. */
  let following = $state(false)

  /** Whether anyone has moved the map by hand since it opened. Until
   *  they have, a first fix arriving late takes the map to it. */
  let touched = false

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

    /* The position alongside the status, so the map opens on the
       car rather than opening somewhere and then flying to it. */
    Promise.all([mapApi.status(), refreshPosition()])
      .then(([info, reading]) => {
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

        const here = located(reading)
          ? ([reading.longitude, reading.latitude] as [number, number])
          : null

        created = new MapLibre({
          container: element,
          style: mapStyle(dark, localLabels),
          center: here ?? START.center,
          zoom: here ? NEAR : START.zoom,
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

        /* Only a drag -- a person moving the map. Zooming keeps the
           car in the middle, which is what zooming while following
           should do. */
        created.on('dragstart', () => {
          touched = true
          following = false
        })

        if (carElement) {
          const moving = new Car(carElement, (next) => (look = next))
          moving.attach(created)
          moving.onmove = (at, first) => follow(at, first)
          car = moving
        }

        /* The pin: point at the bottom, so it marks the spot with its
           tip. Draggable to fine-tune; letting go is the same as
           tapping there. */
        if (pinElement) {
          const marker = new Marker({
            element: pinElement,
            anchor: 'bottom',
            draggable: true,
          })
          marker.on('dragend', () => {
            const at = marker.getLngLat()
            dropAt(at.lat, at.lng)
          })
          pinMarker = marker
        }

        /* A tap: MapLibre does not fire this at the end of a drag or a
           pinch, so moving the map never drops a pin. */
        created.on('click', (event) => tapped(event.lngLat, event.point))

        tripMarkers = new TripMarkers(created)

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
      car?.remove()
      car = undefined
      pinMarker?.remove()
      pinMarker = undefined
      pinShown = false
      tripMarkers?.clear()
      tripMarkers = undefined
      created?.remove()
      map = undefined
    }
  })

  /* The stream, for as long as the screen is open. */
  $effect(() => watchPosition())

  /* Each reading, once there is a map to put it on. untrack: what
     the car and follow() touch is their own business, and reading
     `following` in here would re-run this whenever the locate button
     is pressed. */
  $effect(() => {
    const reading = position.reading
    if (!ready) return
    untrack(() => car?.update(reading))
  })

  function follow(at: [number, number], first: boolean): void {
    if (!map) return

    if (first) {
      /* A fix arriving after the map opened somewhere else -- the GPS
         finding its satellites -- takes the map to the car, unless
         someone has already moved it. */
      if (!touched) {
        following = true
        map.jumpTo({ center: at, zoom: Math.max(map.getZoom(), NEAR) })
      }
      return
    }

    /* Not while the map is already moving -- a zoom in progress, or
       fingers on it. Jumping would cut the zoom off halfway; the car
       is put back in the middle on the next frame after it ends. */
    if (following && !map.isMoving()) map.jumpTo({ center: at })
  }

  /* The pin on the map, wherever it was set -- here, or before the
     screen was last left. untrack: the marker is MapLibre's to move. */
  $effect(() => {
    const pin = destination.pin
    if (!ready) return
    untrack(() => {
      if (!map || !pinMarker) return
      if (!pin) {
        pinMarker.remove()
        pinShown = false
        return
      }
      pinMarker.setLngLat([pin.longitude, pin.latitude])
      if (!pinShown) {
        pinMarker.addTo(map)
        pinShown = true
      }
    })
  })

  /** Over to the pin, at street level. The map stops following the
   *  car, as when it is dragged; the locate button goes back. */
  function focusPin(): void {
    const pin = destination.pin
    if (!map || !pin) return
    following = false
    touched = true
    map.easeTo({
      center: [pin.longitude, pin.latitude],
      zoom: Math.max(map.getZoom(), PIN_ZOOM),
      duration: 700,
    })
  }

  /** A tap on the map: the pin goes there. Unless the search is open,
   *  when the tap only closes it -- tapping away from a list is
   *  dismissing it, not choosing a spot behind it. */
  function tapped(
    at: { lat: number; lng: number },
    point: { x: number; y: number },
  ): void {
    if (typing || listOpen) {
      closeList()
      return
    }

    /* On a grey line: that way, rather than a pin. A margin round the
       tap, because a line is a thin thing to hit with a finger. */
    if (map?.getLayer(ALTERNATIVES)) {
      const near = map.queryRenderedFeatures(
        [
          [point.x - 14, point.y - 14],
          [point.x + 14, point.y + 14],
        ],
        { layers: [ALTERNATIVES] },
      )
      const index = near[0]?.properties?.index
      if (typeof index === 'number') {
        chooseOption(index)
        return
      }
    }

    dropAt(at.lat, at.lng)
  }

  /** The list and the keyboard away without choosing anything. The
   *  field gets the pin's name back if it was emptied to search. */
  function closeList(): void {
    typing = false
    listOpen = false
    results = []
    if (!query.trim() && destination.pin) query = destination.pin.label
  }

  /** The field tapped: keyboard and list up. With a pin showing, its
   *  name is cleared away so the saved places are offered -- the pin
   *  stays, and comes back to the field if nothing else is chosen. */
  function openList(): void {
    if (!listOpen && destination.pin && query === destination.pin.label) {
      query = ''
    }
    typing = true
    listOpen = true
  }

  /** Guidance along the route. Not connected yet: the next step. */
  function start(): void {}

  /* The route's lines, whenever the options or the choice change. */
  $effect(() => {
    const options = trip.options
    const chosen = trip.chosen
    if (!ready) return
    untrack(() => {
      if (map && container) drawRoutes(map, container, options, chosen)
    })
  })

  /* The flag and the stops, whenever the route's places change. */
  $effect(() => {
    const goal = trip.destination
    const stops = trip.stops
    if (!ready) return
    untrack(() => tripMarkers?.update(goal, stops))
  })

  /* A new plan, fitted on screen once: the whole route and the car,
     clear of the cards on the left and the controls on the right. The
     map stops following the car, as when it is dragged. */
  $effect(() => {
    const version = trip.version
    if (!ready || version === fitted) return
    untrack(() => {
      fitted = version
      const route = trip.options[trip.chosen]
      const reading = position.reading
      if (!map || !route) return
      const car: [number, number][] = located(reading)
        ? [[reading.longitude, reading.latitude]]
        : []
      const bounds = boundsOf(route.shape, car)
      if (!bounds) return
      following = false
      touched = true
      map.fitBounds(bounds, {
        /* Below the search field, above the bottom edge with room for
           the car's marker, right of the cards, left of the controls. */
        padding: { top: 120, bottom: 90, left: 400, right: 120 },
        maxZoom: 16,
        duration: 800,
      })
    })
  })

  /* Day and Night. The flavour is a different set of paint values on
     the same layers, so MapLibre diffs it in place -- no flash, and
     the tiles already loaded are kept. */
  $effect(() => {
    const dark = isDark()
    if (!ready || !map || dark === flavour) return
    flavour = dark
    map.setStyle(mapStyle(dark, localLabels))

    /* The new style has no route in it -- the switch replaces
       everything the old one held. Drawn again once it has settled,
       in the new flavour's colours. */
    map.once('idle', () => {
      if (map && container) {
        drawRoutes(map, container, trip.options, trip.chosen)
      }
    })
  })

  const zoomIn = () => map?.zoomIn()
  const zoomOut = () => map?.zoomOut()

  /** To the car, and keep it there. With nothing known about where
   *  the car is, back to where the map opened. */
  function locate(): void {
    if (!map) return
    const reading = position.reading
    if (!located(reading)) {
      map.easeTo({ ...START, duration: 600 })
      return
    }
    following = true
    map.easeTo({
      center: car?.drawn ?? [reading.longitude, reading.latitude],
      zoom: Math.max(map.getZoom(), NEAR),
      duration: 600,
    })
  }
  const faceNorth = () => map?.easeTo({ bearing: 0, duration: 400 })

  const turned = $derived(Math.abs(bearing) > TURNED)

  /** Long enough that the list is not rebuilt mid-word, short enough
   *  that it still feels like it follows the typing. */
  const DEBOUNCE_MS = 220

  let field = $state<HTMLInputElement>()
  /* What the pin is, when there is one -- so coming back to the screen
     shows the same text the pin was chosen with. */
  let query = $state(destination.pin?.label ?? '')
  let typing = $state(false)

  /* The list under the field -- saved places, or suggestions -- has
     its own flag rather than following the keyboard. The keyboard
     closes the moment the field loses focus, and pressing on a list
     entry is exactly what takes the focus away: tied together, the
     list was gone before the tap on it landed. It opens with the
     field, and closes on a choice or a tap on the map. */
  let listOpen = $state(false)

  let results = $state<Address[]>([])
  let searching = $state(false)

  /** Saved places, offered while the field is open and empty. */
  let savedPlaces = $state<Place[]>([])

  /* Fetched each time the field opens, so a place saved in Settings
     since the last time is there. untrack: only opening should run
     this, not the list arriving. */
  $effect(() => {
    if (!listOpen) return
    untrack(() => {
      saved()
        .then((list) => (savedPlaces = list))
        .catch(() => {})
    })
  })

  const showSaved = $derived(
    listOpen && query.trim() === '' && savedPlaces.length > 0,
  )

  /* The field follows the pin: its label when one is chosen, and the
     address once a tapped point's arrives. Not while typing -- that
     text is the person's. */
  $effect(() => {
    const label = destination.pin?.label
    untrack(() => {
      /* And empty once the pin has gone -- into a route, mostly, where
         the route card names it instead. */
      if (!typing && !listOpen) query = label ?? ''
    })
  })

  /** "2.3 km away" from the car, or nothing without a position. */
  function away(latitude: number, longitude: number): string {
    const reading = position.reading
    if (!located(reading)) return ''
    return distanceLabel(
      metresBetween(reading.latitude, reading.longitude, latitude, longitude),
    )
  }

  const pinDistance = $derived(
    destination.pin
      ? away(destination.pin.latitude, destination.pin.longitude)
      : '',
  )

  /** Only from a live fix -- see speedOf. */
  const speed = $derived(speedOf(position.reading))

  /* Debounced, and the result of a stale request is thrown away.
     Without the second part a slow reply for "kun" can land after a
     quick one for "kungsgatan" and replace it. */
  let sequence = 0

  $effect(() => {
    const text = query.trim()

    /* Only while the list is open. The field is also filled in by
       choosing -- with the pin's name -- and searching for that would
       open the list again straight after closing it. */
    if (!listOpen || text.length < MIN_CHARS) {
      /* And any answer still on its way is for a list that has since
         closed: without this it lands afterwards and opens it again. */
      sequence++
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

  /* Choosing either kind of entry works the same: the list and the
     keyboard close, the pin goes there, and the map follows it. The
     field takes the pin's label from the effect above. */
  function choose(place: Address): void {
    results = []
    typing = false
    listOpen = false
    fromSearch(place)
    focusPin()
  }

  function chooseSaved(place: Place): void {
    results = []
    typing = false
    listOpen = false
    fromSaved(place)
    focusPin()
  }

  const capital = (text: string) =>
    text ? text[0].toUpperCase() + text.slice(1) : text

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

  <CarMarker bind:element={carElement} {look} />
  <DestinationPin bind:element={pinElement} />

  <!-- Bottom left, the route above the pin, the column anchored at
       its foot so both grow upwards. Out of the way while the keyboard
       is up, which covers that corner. -->
  {#if !typing && (destination.pin || trip.destination || trip.pending)}
    <div class="cards">
      <RouteCard onstart={start} />

      {#if destination.pin}
        {@const pin = destination.pin}
        <PinCard
          {pin}
          distance={pinDistance}
          routing={hasRoute()}
          busy={trip.planning}
          ondirections={() => planTo(pin)}
          onsetdestination={() => setDestination(pin)}
          onaddstop={() => addStop(pin)}
          onclose={() => {
            clearPin()
            query = ''
          }}
        />
      {/if}
    </div>
  {/if}

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
        onclick={openList}
      />

      {#if searching}
        <Spinner size={18} label="Searching" />
      {:else if query}
        <button
          class="clear"
          aria-label="Clear"
          onclick={() => {
            query = ''
            clearPin()
            field?.focus()
          }}
        >
          <Icon name="close" size={18} />
        </button>
      {/if}
    </div>

    {#if showSaved}
      <ul class="results">
        <li class="heading">Saved places</li>
        <!-- By position: names are whatever was typed when saving. -->
        {#each savedPlaces as place, index (index)}
          <li>
            <button class="result" onclick={() => chooseSaved(place)}>
              <span class="result-title">
                <Icon name="star-filled" size={14} />
                {capital(place.name)}
              </span>
              <span class="result-detail">
                {[place.address, away(place.latitude, place.longitude)]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {:else if results.length}
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
    {:else if listOpen && query.trim().length >= MIN_CHARS && !searching}
      <p class="empty">Nothing found</p>
    {/if}
  </div>

  <div class="speed">
    <span class="figure">{speed ?? '–'}</span>
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
    <!-- To the car, and follow it. Hollow while following -- it is
         already doing what it does -- and filled once the map has
         been dragged away, which is when it is worth pressing. -->
    <button
      class="control primary"
      class:following
      aria-label="Follow the car"
      aria-pressed={following}
      disabled={!ready}
      onclick={locate}
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
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  /* The saved places' star, in the accent like the one that saved
     them on the radio screen. */
  .result-title :global(svg) {
    color: var(--accent);
  }

  .heading {
    padding: var(--spacing-s) var(--spacing) 4px;
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-faint);
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

  /* Bottom left, clear of the attribution in the other corner. Never
     taller than the map below the search field: a long list of stops
     scrolls rather than pushing the top card off the screen. */
  /* Padded, and pulled out by the same amount: a scrolling box clips
     whatever spills over its edge, and without the room the cards'
     shadows were cut off square at the corners. */
  .cards {
    position: absolute;
    left: 6px;
    bottom: 16px;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
    max-height: calc(100% - 86px);
    padding: 12px;
    overflow-y: auto;
  }

  /* In a circle of its own, white by day and black by night, so it
     reads over whatever part of the map is under it. */
  .speed {
    position: absolute;
    top: 18px;
    right: 22px;
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 82px;
    height: 82px;
    justify-content: center;
    border-radius: 50%;
    background: var(--readout);
    /* A light shadow so the circle has an edge where the map under
       it is close to its own colour -- white on a pale Day map. */
    box-shadow: 0 1px 4px rgb(0 0 0 / 0.3);
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

  .control.primary.following {
    color: var(--accent);
    background: color-mix(in srgb, var(--bar) 88%, transparent);
    border-color: var(--accent);
  }

  /* The north half red, as on any compass, so which end is which
     reads without a letter on it. Fixed rather than the accent: red
     for north is a convention, and it should not change with the
     ambient colour or the theme. */
  .compass .north {
    fill: #e0322b;
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
