import * as stored from './api/settings'
import { nav, navigating } from './navigation.svelte'

/* The driving view: how the maps behave while a route is being
   driven -- turned so the road ahead points up, zoomed for the speed
   and in again before each turn.

   Shared by the map screen and the home screen's tile, so that
   tapping the compass on one turns the other north-up as well. The
   two settings come from the daemon; the compass choice lives only
   here, for the drive it was made on. */

interface Store {
  /** navigation.heading_up: heading up from the start of each route. */
  headingUp: boolean
  /** navigation.speed_zoom: zoom with speed, and in before turns. */
  speedZoom: boolean
  /** The route (nav.trip) the compass turned heading-up off for. */
  northUpTrip: number
}

export const driving = $state<Store>({
  headingUp: true,
  speedZoom: true,
  northUpTrip: -1,
})

/** Whether the map should turn with the car right now: navigating,
 *  the setting on, and the compass not pressed on this drive. */
export const headingUpNow = (): boolean =>
  navigating() && driving.headingUp && driving.northUpTrip !== nav.trip

/** The compass: north up for the rest of this drive. */
export function northUp(): void {
  driving.northUpTrip = nav.trip
}

/** The centre button: back to the drive's starting choice. */
export function resumeHeading(): void {
  driving.northUpTrip = -1
}

/** The two settings, from the daemon. Each screen asks as it opens,
 *  so a change made in Settings is in force the next time. */
export async function loadDriving(): Promise<void> {
  try {
    const all = await stored.all()
    driving.headingUp =
      stored.valueAt(all, 'navigation.heading_up') !== false
    driving.speedZoom =
      stored.valueAt(all, 'navigation.speed_zoom') !== false
  } catch {
    // The defaults stand until the next screen opens.
  }
}

/** A setting written from the Settings screen, in force at once. */
export function applyDriving(key: string, value: unknown): void {
  if (key === 'navigation.heading_up') driving.headingUp = value !== false
  if (key === 'navigation.speed_zoom') driving.speedZoom = value !== false
}
