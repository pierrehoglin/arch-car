import * as api from './api/navigation'
import { RequestFailed } from './api/client'
import { clear as clearPin, type Pin } from './destination.svelte'
import type { RouteOption } from './api/navigation'

/* The route: where it goes, the stops on the way, and the ways there
   the router offered.

   Separate from the pin. The pin is for looking at a place; once a
   route exists its destination is fixed, and the pin goes back to
   being free -- tapped around the map, then turned into a new
   destination or a stop when asked.

   Kept here rather than in the map screen, like the pin, so a look at
   another screen does not lose it. A restart does.

   A change is only taken once the router has answered. Until then the
   route on screen stays as it was, and a failure leaves it there with
   the reason beside it -- and the request kept, for Try again. */

/** A place on the route: the destination, or a stop. */
export interface Waypoint {
  latitude: number
  longitude: number
  title: string
  subtitle: string
}

interface Request {
  destination: Waypoint
  stops: Waypoint[]
  /** The pin the request came from, cleared once it is part of the
   *  route -- and left alone if the request fails. */
  fromPin: boolean
}

interface Trip {
  destination: Waypoint | null
  stops: Waypoint[]
  /** The best way first, then any alternatives. */
  options: RouteOption[]
  /** Which of the options is the route. */
  chosen: number
  /** When the router answered, for the arrival time. */
  planned: number | null

  /** A change waiting on the router, or one it refused. */
  pending: Request | null
  planning: boolean
  error: string
  /** Bumped on every new plan, so the map knows to fit it on screen
   *  -- and not when only the chosen option changes. */
  version: number
}

export const trip = $state<Trip>({
  destination: null,
  stops: [],
  options: [],
  chosen: 0,
  planned: null,
  pending: null,
  planning: false,
  error: '',
  version: 0,
})

/* A plan asked for while another is on its way replaces it: only the
   newest answer is taken. */
let ticket = 0

const MESSAGES: Record<api.PlanFailure, string> = {
  position: "Waiting for the car's position.",
  no_route: 'No road route to this place.',
  offline: 'Routing needs an internet connection.',
  other: 'The route could not be planned.',
}

function waypoint(pin: Pin): Waypoint {
  return {
    latitude: pin.latitude,
    longitude: pin.longitude,
    title: pin.title || pin.label,
    subtitle: pin.subtitle,
  }
}

async function request(next: Request): Promise<void> {
  const mine = ++ticket
  trip.pending = next
  trip.planning = true
  trip.error = ''

  try {
    const found = await api.plan(next.destination, next.stops)
    if (mine !== ticket) return

    trip.destination = next.destination
    trip.stops = next.stops
    trip.options = found.routes
    trip.chosen = 0
    trip.planned = Date.now()
    trip.pending = null
    trip.version++
    if (next.fromPin) clearPin()
  } catch (cause) {
    if (mine !== ticket) return
    trip.error =
      cause instanceof RequestFailed
        ? cause.status === 0
          ? 'The car service did not answer.'
          : MESSAGES[api.failureFor(cause.status)]
        : MESSAGES.other
  } finally {
    if (mine === ticket) trip.planning = false
  }
}

/** Is there a route? Not counting one still being asked for. */
export const hasRoute = () => trip.destination !== null

/** Directions from the pin, when there is no route yet. */
export function planTo(pin: Pin): Promise<void> {
  return request({ destination: waypoint(pin), stops: [], fromPin: true })
}

/** The pin becomes the destination. The stops stay. */
export function setDestination(pin: Pin): Promise<void> {
  return request({
    destination: waypoint(pin),
    stops: [...trip.stops],
    fromPin: true,
  })
}

/** The pin becomes a stop, after any already on the route. */
export function addStop(pin: Pin): Promise<void> {
  if (!trip.destination) return planTo(pin)
  return request({
    destination: trip.destination,
    stops: [...trip.stops, waypoint(pin)],
    fromPin: true,
  })
}

export function removeStop(index: number): Promise<void> {
  if (!trip.destination) return Promise.resolve()
  return request({
    destination: trip.destination,
    stops: trip.stops.filter((_, i) => i !== index),
    fromPin: false,
  })
}

/** The request that failed, again. */
export function retry(): Promise<void> {
  return trip.pending ? request(trip.pending) : Promise.resolve()
}

/** Leave a failed change. What was on screen before stays. */
export function dismiss(): void {
  ticket++
  trip.pending = null
  trip.planning = false
  trip.error = ''
}

export function choose(index: number): void {
  if (index >= 0 && index < trip.options.length) trip.chosen = index
}

/** No route any more: destination, stops and lines gone. */
export function end(): void {
  ticket++
  trip.destination = null
  trip.stops = []
  trip.options = []
  trip.chosen = 0
  trip.planned = null
  trip.pending = null
  trip.planning = false
  trip.error = ''
}
