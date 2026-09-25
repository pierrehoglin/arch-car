import { request } from './client'
import type { NowPlaying } from './types'

/* Media, for whichever transport a source is on.
 *
 * The daemon takes `bluetooth`, `spotify`, or an MPRIS player name,
 * and answers in one shape either way -- so a screen differs only in
 * which source it asks about.
 */

export type Action =
  | 'play'
  | 'pause'
  | 'stop'
  | 'next'
  | 'prev'
  | 'forward'
  | 'rewind'

export const now = (source: string) =>
  request<NowPlaying>(`/media/${source}`)

/** Move to a point in the track, in milliseconds. MPRIS only. */
export const seek = (source: string, ms: number) =>
  request<NowPlaying>(`/media/${source}/position`, {
    method: 'POST',
    body: { ms },
  })

export const command = (source: string, action: Action) =>
  request<NowPlaying>(`/media/${source}/${action}`, { method: 'POST' })
