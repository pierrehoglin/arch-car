import { Marker, type Map as MapLibre } from 'maplibre-gl'
import { metresBetween } from '../address'
import { located } from '../position.svelte'
import type { Position } from '../api/types'

/* The car on a map: where the marker is drawn, which way it points,
 * and how it gets from one GPS reading to the next.
 *
 * Shared by the map screen and the home screen's map tile, so the two
 * cannot disagree about where the car is or how it moves. What the
 * map itself does about it -- follow, or not -- is the screen's
 * business, told through `onmove`.
 */

/** Below this the GPS heading is noise -- a parked receiver reports
 *  whichever way the jitter happens to point -- so the arrow keeps
 *  the last direction it had while moving. */
export const MOVING_KMH = 5

/** Further than this between two readings is a jump, not a drive:
 *  the first fix after a remembered position, or a pin changed.
 *  Gliding across it would sweep the map through the country. */
export const JUMP_METRES = 500

/** How long the car takes to glide to a new reading. The GPS
 *  refreshes once a second, so this keeps it moving smoothly from one
 *  to the next instead of hopping a few car lengths at a time. */
export const GLIDE_MS = 1000

/** How the marker should look. Reported, not applied: the element
 *  belongs to a Svelte component, which draws it from these. */
export interface CarLook {
  source: Position['source']
  /** An arrow rather than a dot: the car has moved, so there is a
   *  direction to show. */
  pointing: boolean
}

/** How a small map is getting on, for the tile around it: a plain
 *  tile until there is a map to show, and for good if there is none. */
export type CarMapStatus = 'loading' | 'ready' | 'unavailable'

type LngLat = [number, number]

/** The shorter way round from one heading to another. */
function turn(from: number, to: number, t: number): number {
  const delta = ((to - from + 540) % 360) - 180
  return (from + delta * t + 360) % 360
}

export class Car {
  /** Where the marker is drawn now, mid-glide included. Null while
   *  it is not on the map. */
  drawn: LngLat | null = null

  /** Each position drawn: once when the car first appears (`first`),
   *  then every frame of every glide. */
  onmove: ((at: LngLat, first: boolean) => void) | undefined

  private readonly marker: Marker
  private map: MapLibre | undefined
  private heading: number | null = null
  private drawnHeading = 0
  private frame = 0
  private glide: {
    from: LngLat
    to: LngLat
    fromHeading: number
    toHeading: number
    start: number
    duration: number
  } | null = null

  constructor(
    element: HTMLElement,
    private readonly onlook: (look: CarLook) => void,
  ) {
    /* rotationAlignment 'map': the heading is relative to north, and
       MapLibre turns the arrow with the map when it is rotated -- no
       arithmetic with the bearing here. */
    this.marker = new Marker({
      element,
      rotationAlignment: 'map',
      pitchAlignment: 'map',
    })
  }

  /** Which way the arrow points as drawn, mid-turn included -- what a
   *  heading-up map turns to. Null until the car has moved, when
   *  there is no direction to point the map in. */
  get bearing(): number | null {
    return this.heading === null ? null : this.drawnHeading
  }

  attach(map: MapLibre): void {
    this.map = map
  }

  /** A new reading. Places, glides, jumps or hides the marker. */
  update(reading: Position | null): void {
    const map = this.map
    if (!map) return

    if (!located(reading)) {
      this.hide()
      this.onlook({ source: 'none', pointing: false })
      return
    }

    const target: LngLat = [reading.longitude, reading.latitude]

    if (
      reading.source === 'gps' &&
      typeof reading.heading === 'number' &&
      (reading.speed_kmh ?? 0) >= MOVING_KMH
    ) {
      this.heading = reading.heading
    }
    this.onlook({ source: reading.source, pointing: this.heading !== null })

    if (!this.drawn) {
      this.drawn = target
      this.drawnHeading = this.heading ?? 0
      this.marker.setLngLat(target).setRotation(this.drawnHeading).addTo(map)
      this.onmove?.(target, true)
      return
    }

    const [lon, lat] = this.drawn
    const far = metresBetween(lat, lon, target[1], target[0]) > JUMP_METRES

    this.glide = {
      from: this.drawn,
      to: target,
      fromHeading: this.drawnHeading,
      toHeading: this.heading ?? this.drawnHeading,
      start: performance.now(),
      duration: far ? 0 : GLIDE_MS,
    }
    if (!this.frame) this.frame = requestAnimationFrame(this.step)
  }

  /** Off the map, and every animation stopped. For teardown. */
  remove(): void {
    this.hide()
    this.map = undefined
  }

  private hide(): void {
    cancelAnimationFrame(this.frame)
    this.frame = 0
    this.glide = null
    this.marker.remove()
    this.drawn = null
  }

  /* An arrow function, so requestAnimationFrame can be handed it
     without losing `this`. */
  private step = (now: number): void => {
    this.frame = 0
    const glide = this.glide
    if (!glide || !this.map) return

    const t = glide.duration
      ? Math.min(1, (now - glide.start) / glide.duration)
      : 1
    const { from, to } = glide
    const at: LngLat = [
      from[0] + (to[0] - from[0]) * t,
      from[1] + (to[1] - from[1]) * t,
    ]
    this.drawn = at
    this.drawnHeading = turn(glide.fromHeading, glide.toHeading, t)
    this.marker.setLngLat(at).setRotation(this.drawnHeading)
    this.onmove?.(at, false)

    if (t < 1) this.frame = requestAnimationFrame(this.step)
    else this.glide = null
  }
}
