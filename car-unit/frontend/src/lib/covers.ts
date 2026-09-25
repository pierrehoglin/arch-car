import bluetoothCover from './assets/bluetooth-cover.jpg'
import type { NowPlaying } from './api/types'

/* Cover art, and what to show where there is none.
 *
 * AVRCP does not carry artwork: the profile can, over a separate
 * channel, but BlueZ does not expose it -- so a phone playing over
 * Bluetooth has a title and an artist and nothing to look at. A
 * picture of our own fills that, rather than leaving the tile blank
 * or inventing a coloured square.
 *
 * Imported rather than referenced by path, so the build fails if the
 * file is missing instead of the car showing a broken image. Vite
 * hashes the filename, which also means a replacement is picked up
 * without anything having to clear a cache.
 */

/** By source name, for the ones that never publish any. */
const FALLBACKS: Record<string, string> = {
  bluetooth: bluetoothCover,
}

/**
 * What to show for a player.
 *
 * Whatever it published, then ours, then nothing -- a source with
 * neither gets no artwork at all, which the screens handle.
 */
export function coverFor(player: NowPlaying | null): string {
  if (!player) return ''
  return player.art || FALLBACKS[player.source] || ''
}
