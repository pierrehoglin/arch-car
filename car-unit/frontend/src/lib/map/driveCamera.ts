import type { JumpToOptions, Map as MapLibre, PaddingOptions } from 'maplibre-gl'

/* Where the camera goes while a route is being driven: the zoom for
   the speed, nearer before a turn, and the car low on the screen when
   the map turns with it.

   The zoom is followed rather than set: the speed is smoothed over a
   few seconds and the zoom moves towards its target at a steady pace,
   so stop-and-go traffic does not pump the map in and out, and a
   change of speed is felt as the map drawing back rather than
   jumping. */

/** Zoom at a speed, between the points given, and the zoom for an
 *  approaching turn. */
export interface ZoomRange {
  stops: [kmh: number, zoom: number][]
  turn: number
}

/** The map screen. */
export const SCREEN: ZoomRange = {
  stops: [
    [30, 17],
    [50, 16],
    [80, 15],
    [110, 14],
  ],
  turn: 17,
}

/** The home tile: small, so never as far out, nor as far in. */
export const TILE: ZoomRange = {
  stops: [
    [30, 16],
    [60, 15],
    [100, 14],
  ],
  turn: 16,
}

/** Nearer than this, the next turn or stop has the zoom. */
export const TURN_METRES = 400

/** How long a change of speed takes to be believed, in seconds. */
const SPEED_SECONDS = 4

/** How fast the zoom moves towards its target, in levels a second:
 *  slowly with the speed, quicker for a turn coming up. */
const ZOOM_RATE = 0.5
const TURN_RATE = 1

/** How far down the screen the car sits when the map turns with it:
 *  the top padding that puts the centre there. 0.4 of the height
 *  above leaves the car at 70%, with the road ahead above it. */
const LOW = 0.4

export function zoomFor(kmh: number, range: ZoomRange): number {
  const stops = range.stops
  if (kmh <= stops[0][0]) return stops[0][1]
  for (let i = 1; i < stops.length; i++) {
    const [k1, z1] = stops[i]
    const [k0, z0] = stops[i - 1]
    if (kmh <= k1) return z0 + ((z1 - z0) * (kmh - k0)) / (k1 - k0)
  }
  return stops[stops.length - 1][1]
}

export class ZoomFollower {
  private speed: number | null = null
  private zoom: number | null = null
  private last = 0

  constructor(private readonly range: ZoomRange) {}

  private goal(nextMetres: number | null): number {
    if (nextMetres !== null && nextMetres < TURN_METRES) return this.range.turn
    return zoomFor(this.speed ?? 0, this.range)
  }

  /** Straight to the target, for the camera easing into the view:
   *  there is nothing to smooth from. */
  settle(kmh: number | null, nextMetres: number | null): number {
    this.speed = kmh ?? this.speed
    this.last = performance.now()
    this.zoom = this.goal(nextMetres)
    return this.zoom
  }

  /** One frame's worth of the way towards the target. */
  step(kmh: number | null, nextMetres: number | null): number {
    const now = performance.now()
    /* Capped: frames stop while the car stands still, and the first
       one after a long wait is not a long step. */
    const dt = Math.min(0.5, Math.max(0, (now - this.last) / 1000))
    this.last = now

    if (kmh !== null) {
      this.speed =
        this.speed === null
          ? kmh
          : this.speed + (kmh - this.speed) * (1 - Math.exp(-dt / SPEED_SECONDS))
    }

    const goal = this.goal(nextMetres)
    if (this.zoom === null) this.zoom = goal
    const approaching = nextMetres !== null && nextMetres < TURN_METRES
    const most = (approaching ? TURN_RATE : ZOOM_RATE) * dt
    this.zoom += Math.max(-most, Math.min(most, goal - this.zoom))
    return this.zoom
  }
}

export const NO_PADDING: PaddingOptions = { top: 0, bottom: 0, left: 0, right: 0 }

/** The padding that puts the car low, or none. */
export function paddingFor(map: MapLibre, low: boolean): PaddingOptions {
  if (!low) return NO_PADDING
  return { ...NO_PADDING, top: Math.round(map.getContainer().clientHeight * LOW) }
}

/** The whole camera for one moment of the drive. */
export function driveCamera(
  map: MapLibre,
  at: [number, number],
  bearing: number | null,
  headingUp: boolean,
  zoom: number | null,
): JumpToOptions {
  return {
    center: at,
    bearing: headingUp ? (bearing ?? map.getBearing()) : 0,
    zoom: zoom ?? map.getZoom(),
    padding: paddingFor(map, headingUp),
  }
}
