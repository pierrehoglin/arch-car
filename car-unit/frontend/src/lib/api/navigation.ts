import { request } from './client'

/* Route planning, against the daemon's /navigate endpoints.

   The daemon starts every route from its own idea of where the car
   is, so only the destination and the stops are sent. */

export interface LatLon {
  latitude: number
  longitude: number
}

/** One way there. */
export interface RouteOption {
  /** Metres. */
  distance: number
  /** Seconds, as the router estimates it. */
  time: number
  /** [lon, lat] pairs, ready for GeoJSON. */
  shape: [number, number][]
}

export interface Plan {
  start: LatLon
  /** The best first, then any alternatives -- only when there are no
   *  stops, which the router cannot offer alternatives through. */
  routes: RouteOption[]
}

/** Why a plan failed, from the status the daemon answers with. */
export type PlanFailure = 'position' | 'no_route' | 'offline' | 'other'

export const failureFor = (status: number): PlanFailure =>
  status === 409
    ? 'position'
    : status === 422
      ? 'no_route'
      : status === 503
        ? 'offline'
        : 'other'

const point = (p: LatLon) => ({ lat: p.latitude, lon: p.longitude })

export const plan = (destination: LatLon, stops: LatLon[] = []) =>
  request<Plan>('/navigate/plan', {
    method: 'POST',
    body: { destination: point(destination), stops: stops.map(point) },
    /* The router is paced to a call a second and a long route takes a
       moment to work out over a cellular link. */
    timeout: 30_000,
  })

/* --- Navigating ---------------------------------------------------- */

/** A destination or stop, as the daemon keeps it while navigating. */
export interface NavPlace {
  latitude: number
  longitude: number
  title: string
  subtitle: string
}

/** One turn still ahead. */
export interface NavStep {
  /** Valhalla's maneuver type -- see map/turnIcons. */
  kind: number
  instruction: string
  street: string
  /** Metres from the car to where it happens. */
  distance: number
  /** Set on a stop's arrival: which stop, 1 for the next. */
  stop?: number
  title?: string
}

export type NavStateName =
  | 'idle'
  | 'resuming'
  | 'navigating'
  | 'rerouting'
  | 'offline'
  | 'arrived'

/** The 'navigation' event, about once a second while driving. */
export interface NavState {
  state: NavStateName
  /** Changes when the route itself does: fetch its line again. */
  version: number
  /** Picked up again after the car was off. */
  resumed?: boolean
  /** "Rerouting…", "Off route — …", "Resuming route · …". */
  message?: string
  destination?: NavPlace
  /** Still to visit, in order. */
  stops?: NavPlace[]
  /** Metres and seconds left. */
  remaining?: number
  remaining_time?: number
  next?: NavStep | null
  /** The turn after the next, when it comes close behind it. */
  then?: NavStep | null
  steps?: NavStep[]
  on_route?: boolean
  /** Where the car is on the route line, and which way the road goes
   *  there -- for the marker, while close to the route. */
  snapped?: { latitude: number; longitude: number; bearing: number | null } | null
  /** The route segment the car is on, for fading what is driven. */
  index?: number
}

/** The session with the route's line, as [lon, lat]. */
export interface NavDetail extends NavState {
  shape: [number, number][]
}

const place = (p: NavPlace) => ({
  latitude: p.latitude,
  longitude: p.longitude,
  title: p.title,
  subtitle: p.subtitle,
})

/** Follow one of the last plan's routes. */
export const start = (choice: number, destination: NavPlace, stops: NavPlace[]) =>
  request<NavDetail>('/navigate/start', {
    method: 'POST',
    body: { choice, destination: place(destination), stops: stops.map(place) },
  })

/** A new destination or new stops while navigating. */
export const update = (destination: NavPlace, stops: NavPlace[]) =>
  request<NavDetail>('/navigate/update', {
    method: 'POST',
    body: { destination: place(destination), stops: stops.map(place) },
    timeout: 30_000,
  })

export const end = () => request<NavDetail>('/navigate/end', { method: 'POST' })

export const session = () => request<NavDetail>('/navigate/session')
