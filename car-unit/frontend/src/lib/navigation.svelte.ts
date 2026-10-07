import * as api from './api/navigation'
import { RequestFailed } from './api/client'
import { on } from './api/stream.svelte'
import { clear as clearPin, type Pin } from './destination.svelte'
import { end as endPlan, trip } from './route.svelte'
import type { NavPlace, NavState } from './api/navigation'
import type { Position } from './api/types'

/* Navigating, as the screens see it.

   The daemon does the following -- this mirrors its 'navigation'
   event, plus the route's line, which the event leaves out to stay
   small and which is fetched once each time the route changes.

   Kept here rather than in the map screen so the home screen, or any
   other, can show the same session. */

interface Store {
  /** The last event, or null before one has arrived. */
  session: NavState | null
  /** The route being driven, as [lon, lat]. */
  shape: [number, number][]
  /** Which route `shape` is: the session's version when it was fetched. */
  shapeVersion: number
  /** Every step in the card, or only the next two. Remembered across
   *  screens, like the rest of this. */
  showAll: boolean
  /** A change asked for while driving -- start, a new destination, a
   *  stop -- and still waiting on the router. */
  busy: boolean
  error: string
  /** Counts routes: one more each time navigating starts, from
   *  nothing to something. What a choice made for "this drive" --
   *  the compass turning heading-up off -- is tied to, so the next
   *  route starts fresh without anyone having to clear it. */
  trip: number
}

export const nav = $state<Store>({
  session: null,
  shape: [],
  shapeVersion: -1,
  showAll: false,
  busy: false,
  error: '',
  trip: 0,
})

/** Whether there is a session to show: anything but idle. */
export const navigating = () =>
  !!nav.session && nav.session.state !== 'idle'

/** How near the next turn has to be for its banner to show. Further
 *  off, there is nothing to do yet, and the map is worth more than a
 *  banner saying so. */
export const TURN_SHOWN_WITHIN = 5000

/** Whether to show the turn banner. Rerouting, off route, waiting for
 *  GPS and arriving are always said: those are news whatever the
 *  distance. */
export function turnShown(): boolean {
  const session = nav.session
  if (!session || !navigating()) return false
  if (session.state !== 'navigating') return true
  return !!session.next && session.next.distance < TURN_SHOWN_WITHIN
}

/** Where to draw the car. On the route line while navigating and
 *  close to it -- the daemon says when it is, by the same off-route
 *  distance it reroutes at -- with the arrow along the road. Further
 *  away, or not navigating, the GPS as it is, so the marker shows
 *  where the car really went. */
export function onRoute(reading: Position | null): Position | null {
  const session = nav.session
  if (!reading || !navigating() || !session?.on_route || !session.snapped) {
    return reading
  }
  return {
    ...reading,
    latitude: session.snapped.latitude,
    longitude: session.snapped.longitude,
    heading: session.snapped.bearing ?? reading.heading,
  }
}

/** The session from the daemon, counting a route that has begun. */
function setSession(state: NavState): void {
  const was = navigating()
  nav.session = state
  if (!was && navigating()) nav.trip++
}

function take(detail: api.NavDetail): void {
  const { shape, ...state } = detail
  setSession(state)
  nav.shape = shape
  nav.shapeVersion = state.version
}

function failure(cause: unknown): string {
  if (!(cause instanceof RequestFailed)) return 'That did not work.'
  if (cause.status === 0) return 'The car service did not answer.'
  return (
    {
      position: "Waiting for the car's position.",
      no_route: 'No road route to this place.',
      offline: 'Routing needs an internet connection.',
      other: 'That did not work.',
    } as const
  )[api.failureFor(cause.status)]
}

/** The full session, line included. Once on opening, and whenever an
 *  event says the route has changed. */
export async function refresh(): Promise<void> {
  try {
    take(await api.session())
  } catch {
    // Left to the next event.
  }
}

/** Follow the daemon. Returns the unsubscribe, for an $effect. */
export function watch(): () => void {
  return on('navigation', (data) => {
    const state = data as NavState
    setSession(state)
    if (state.state === 'idle') {
      nav.shape = []
      nav.shapeVersion = state.version
    } else if (state.version !== nav.shapeVersion) {
      refresh()
    }
  })
}

async function run(action: () => Promise<api.NavDetail>): Promise<boolean> {
  nav.busy = true
  nav.error = ''
  try {
    take(await action())
    return true
  } catch (cause) {
    nav.error = failure(cause)
    return false
  } finally {
    nav.busy = false
  }
}

/** Start the planned route -- the chosen one of the options. The plan
 *  is done with once the daemon is following it. */
export async function start(): Promise<boolean> {
  const goal = trip.destination
  if (!goal) return false
  const started = await run(() => api.start(trip.chosen, goal, trip.stops))
  if (started) endPlan()
  return started
}

function placeOf(pin: Pin): NavPlace {
  return {
    latitude: pin.latitude,
    longitude: pin.longitude,
    title: pin.title || pin.label,
    subtitle: pin.subtitle,
  }
}

/** The pin becomes where the drive ends. The stops stay. */
export async function setDestination(pin: Pin): Promise<void> {
  const stops = nav.session?.stops ?? []
  if (await run(() => api.update(placeOf(pin), stops))) clearPin()
}

/** The pin becomes the last stop before the destination. */
export async function addStop(pin: Pin): Promise<void> {
  const goal = nav.session?.destination
  if (!goal) return
  const stops = [...(nav.session?.stops ?? []), placeOf(pin)]
  if (await run(() => api.update(goal, stops))) clearPin()
}

export async function removeStop(index: number): Promise<void> {
  const goal = nav.session?.destination
  if (!goal) return
  const stops = (nav.session?.stops ?? []).filter((_, i) => i !== index)
  await run(() => api.update(goal, stops))
}

/** Stop navigating -- or, once arrived, done. */
export async function end(): Promise<void> {
  await run(() => api.end())
}

export function dismissError(): void {
  nav.error = ''
}
