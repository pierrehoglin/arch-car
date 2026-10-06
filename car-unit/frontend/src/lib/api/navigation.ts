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
