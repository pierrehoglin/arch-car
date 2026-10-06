<script lang="ts">
  import { untrack } from 'svelte'
  import { Map as MapLibre } from 'maplibre-gl'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import * as mapApi from '$lib/api/map'
  import { isDark } from '$lib/settings.svelte'
  import {
    located,
    position,
    refresh as refreshPosition,
    watch as watchPosition,
  } from '$lib/position.svelte'
  import {
    nav,
    navigating,
    onRoute,
    refresh as refreshNav,
    watch as watchNav,
  } from '$lib/navigation.svelte'
  import { mapStyle, registerProtocol } from './style'
  import { Car, type CarLook, type CarMapStatus } from './car'
  import CarMarker from './CarMarker.svelte'
  import { drawRoutes, splitAt } from './routeLines'
  import { TripMarkers } from './tripMarkers'

  /* A map that only shows where the car is: always centred on it,
     north up, and not to be touched -- a glance, not a tool. The map
     screen is one tap away for anything more.

     And the route being driven, when there is one: the line ahead,
     what has been driven faded, the flag and the stops -- as the map
     screen draws them. Only a route being driven; a plan not started
     stays on the map screen.

     Fills its parent. Says how it is getting on through `status`, so
     the tile around it can stay a plain tile when there is no map. */

  interface Props {
    /** Streets with their names by default; the tile is small, so
     *  anything wider loses the car in the town. */
    zoom?: number
    status?: CarMapStatus
    look?: CarLook
  }

  let {
    zoom = 15,
    status = $bindable('loading'),
    look = $bindable({ source: 'none', pointing: false }),
  }: Props = $props()

  /** Where the map sits with nothing known about the car at all. */
  const START: [number, number] = [18.0686, 59.3293]

  let container = $state<HTMLDivElement>()
  let carElement = $state<HTMLDivElement>()

  /* Plain: MapLibre owns its own state. */
  let map: MapLibre | undefined
  let car: Car | undefined
  let tripMarkers: TripMarkers | undefined
  let flavour: boolean | null = null
  let localLabels = false

  $effect(() => {
    const element = container
    if (!element) return

    let cancelled = false
    let created: MapLibre | undefined

    Promise.all([mapApi.status(), refreshPosition()])
      .then(([info, reading]) => {
        if (cancelled) return
        if (!info.available) {
          status = 'unavailable'
          return
        }

        registerProtocol()
        const dark = untrack(isDark)
        flavour = dark
        localLabels = info.labels.available

        const here = located(reading)
          ? ([reading.longitude, reading.latitude] as [number, number])
          : null

        created = new MapLibre({
          container: element,
          style: mapStyle(dark, localLabels),
          center: here ?? START,
          zoom: here ? zoom : 12,
          /* Nothing to drag, pinch or turn: the map follows the car,
             and a touch on it is a tap on the tile around it. */
          interactive: false,
          attributionControl: false,
        })

        if (carElement) {
          const moving = new Car(carElement, (next) => (look = next))
          moving.attach(created)
          /* Every frame, without exception. Nobody can move this map,
             so there is nothing to wait for or step aside from. */
          moving.onmove = (at, first) =>
            created?.jumpTo(first ? { center: at, zoom } : { center: at })
          car = moving
        }

        tripMarkers = new TripMarkers(created)

        created.on('load', () => {
          if (cancelled) return
          /* The effect below places the car from here on. */
          status = 'ready'
        })

        created.on('error', (event) => {
          const url = (event.error as { url?: string } | undefined)?.url ?? ''
          const elsewhere =
            /^https?:/.test(url) && !url.startsWith(location.origin)
          console.warn('home map:', event.error?.message ?? event)
          /* Before it has drawn anything, a failure means no map: the
             tile goes back to being a plain link rather than showing
             a grey box. Missing label fonts from the internet are not
             that -- the map still draws without names. */
          if (status !== 'ready' && !elsewhere && !cancelled) {
            status = 'unavailable'
          }
        })

        map = created
      })
      .catch((cause) => {
        if (cancelled) return
        console.warn('home map:', cause)
        status = 'unavailable'
      })

    return () => {
      cancelled = true
      flavour = null
      car?.remove()
      car = undefined
      tripMarkers?.clear()
      tripMarkers = undefined
      created?.remove()
      map = undefined
      status = 'loading'
    }
  })

  $effect(() => watchPosition())

  /* The navigation session: the whole of it once, then the events. */
  $effect(() => {
    refreshNav()
    return watchNav()
  })

  /* On the route line while following it, as on the map screen. */
  const carReading = $derived(onRoute(position.reading))

  $effect(() => {
    const reading = carReading
    if (status !== 'ready') return
    untrack(() => car?.update(reading))
  })

  /** The route ahead and behind, or nothing when not navigating. */
  function drawLines(): void {
    if (!map || !container) return
    if (navigating() && nav.shape.length) {
      const session = nav.session
      const at: [number, number] | null = session?.snapped
        ? [session.snapped.longitude, session.snapped.latitude]
        : null
      const { driven, ahead } = splitAt(nav.shape, session?.index ?? 0, at)
      drawRoutes(map, container, [{ shape: ahead, distance: 0, time: 0 }], 0, driven)
    } else if (map.getSource('trip')) {
      drawRoutes(map, container, [], 0)
    }
  }

  /* About once a second while driving: the fading keeping up. */
  $effect(() => {
    void [nav.session, nav.shape]
    if (status !== 'ready') return
    untrack(drawLines)
  })

  $effect(() => {
    const active = navigating()
    const goal = active ? (nav.session?.destination ?? null) : null
    const stops = active ? (nav.session?.stops ?? []) : []
    if (status !== 'ready') return
    untrack(() => tripMarkers?.update(goal, stops))
  })

  $effect(() => {
    const dark = isDark()
    if (status !== 'ready' || !map || dark === flavour) return
    flavour = dark
    map.setStyle(mapStyle(dark, localLabels))
    /* The new style has no route in it; drawn again once it settles. */
    map.once('idle', drawLines)
  })
</script>

<div class="car-map" bind:this={container}></div>
<CarMarker bind:element={carElement} {look} size={40} />

<style>
  .car-map {
    position: absolute;
    inset: 0;
  }
</style>
