import * as api from './api/position'
import { on } from './api/stream.svelte'
import type { Position } from './api/types'

/* Where the car is, kept current from the event stream.
 *
 * The daemon publishes when the reading would draw differently --
 * about once a second while driving, and not at all while parked --
 * so this is a mirror, not a poll.
 */

export const position = $state<{ reading: Position | null }>({
  reading: null,
})

/** Coordinates, when there are any to draw. */
export function located(
  reading: Position | null,
): reading is Position & { latitude: number; longitude: number } {
  return (
    !!reading &&
    reading.source !== 'none' &&
    typeof reading.latitude === 'number' &&
    typeof reading.longitude === 'number'
  )
}

/** Whole km/h, only from a live fix. Null otherwise: a remembered
 *  or pinned position has no speed, and the screens show a dash
 *  rather than a zero that looks like a reading. */
export function speedOf(reading: Position | null): number | null {
  if (reading?.source !== 'gps' || typeof reading.speed_kmh !== 'number') {
    return null
  }
  return Math.round(reading.speed_kmh)
}

/** Fetch once, for a screen that wants a position before the stream
 *  has said anything. Failures are left to the stream to make up. */
export async function refresh(): Promise<Position | null> {
  try {
    const reading = await api.get()
    /* The stream may have delivered something newer while this was
       in flight; its reading wins. */
    position.reading ??= reading
    return position.reading
  } catch {
    return position.reading
  }
}

/** Follow the stream. Returns the unsubscribe, for an $effect. */
export function watch(): () => void {
  return on('position', (data) => {
    position.reading = data as Position
  })
}
