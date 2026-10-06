import { current } from './api/places'
import { on } from './api/stream.svelte'
import type { Place } from './api/types'

/* Where the car is, in words: the current position with its address.

   The daemon publishes a 'place' event when the address changes --
   not when the position does, which is every second while driving --
   so this is a mirror of that, plus one fetch for a screen opening
   before anything has been published. The fetch is also what asks
   for an address when there is none yet; see /places/current. */

export const here = $state<{ place: Place | null; loaded: boolean }>({
  place: null,
  loaded: false,
})

/** Fetch once. Failures are left to the stream to make up. */
export async function refresh(): Promise<void> {
  try {
    here.place = await current()
  } catch {
    // No daemon, or no position yet. The event fills it in later.
  } finally {
    here.loaded = true
  }
}

/** Follow the stream. Returns the unsubscribe, for an $effect. */
export function watch(): () => void {
  return on('place', (data) => {
    here.place = data as Place | null
    here.loaded = true
  })
}
