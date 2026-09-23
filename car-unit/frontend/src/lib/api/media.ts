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

export const command = (source: string, action: Action) =>
  request<NowPlaying>(`/media/${source}/${action}`, { method: 'POST' })
