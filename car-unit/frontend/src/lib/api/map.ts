import { request } from './client'

/* The offline map. The daemon serves one PMTiles archive; the browser
 * reads the tiles out of it itself, in byte ranges, so the only call
 * here is asking whether there is one. */

export interface MapInfo {
  available: boolean
  /** Where the daemon looks for it, for the message when it is not
   *  there. */
  path: string
  size_bytes: number
  /** west, south, east, north -- the area the archive covers. */
  bounds: [number, number, number, number]
  /** How to make one, when there is none. */
  hint: string
}

export const status = () => request<MapInfo>('/map')

/** Relative, like every other API path. Made absolute where it is
 *  used, because the pmtiles:// protocol needs a full URL. */
export const TILES_PATH = '/api/map/tiles.pmtiles'
