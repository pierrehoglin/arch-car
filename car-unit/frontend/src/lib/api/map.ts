import { request } from './client'

/* The offline map and its labels: what is installed, what is newest,
 * and downloading either. The tiles themselves are not fetched
 * through here -- MapLibre reads them straight out of the archive in
 * byte ranges -- and neither are the fonts and icons, which the map
 * style points at directly. */

export interface MapBuild {
  key: string
  /** 2026-10-05 */
  build: string
  version: string
  planet_bytes: number
}

export interface MapJob {
  kind: 'tiles' | 'labels'
  phase:
    | 'starting'
    | 'checking'
    | 'downloading'
    | 'installing'
    | 'done'
    | 'failed'
    | 'cancelled'
  percent: number
  /** "580 MB/1.4 GB, 9.1 MB/s" for tiles, "312 of 776" for labels. */
  detail: string
  build: string
  maxzoom: number | null
  expected_bytes: number
  started: number
  finished: number | null
  error: string
}

export interface MapInfo {
  available: boolean
  /** Where the daemon looks for it, for the message when it is not
   *  there. */
  path: string
  size_bytes: number
  /** west, south, east, north -- the area the archive covers. */
  bounds: [number, number, number, number]
  /** What to do when there is no map. */
  hint: string
  /** Which planet build it was cut from. Empty for a file put there
   *  by hand. */
  build: string
  maxzoom: number | null
  /** Unix seconds. */
  installed: number | null
  labels: {
    available: boolean
    size_bytes: number
    installed: number | null
  }
  /** The pmtiles tool, which tile downloads need. */
  tool: { available: boolean; hint: string }
  /** Null until it has been looked up. */
  latest: MapBuild | null
  detail_levels: number[]
  /** The last detail chosen. */
  maxzoom_setting: number
  job: MapJob | null
}

export interface MapEstimate {
  maxzoom: number
  bytes: number
  build: string
}

export const status = () => request<MapInfo>('/map')

/** Ask what the newest build is. Needs the internet. */
export const checkLatest = () =>
  request<MapInfo>('/map/latest', { method: 'POST', timeout: 30_000 })

/** Reads the build's index, so seconds rather than milliseconds. */
export const estimate = (maxzoom: number) =>
  request<MapEstimate>('/map/estimate', {
    query: { maxzoom },
    timeout: 130_000,
  })

export const download = (maxzoom: number) =>
  request<MapInfo>('/map/download', { method: 'POST', body: { maxzoom } })

export const downloadLabels = () =>
  request<MapInfo>('/map/labels/download', { method: 'POST' })

export const cancel = () => request<MapInfo>('/map/cancel', { method: 'POST' })

/** Relative, like every other API path. Made absolute where it is
 *  used, because the pmtiles:// protocol needs a full URL. */
export const TILES_PATH = '/api/map/tiles.pmtiles'
export const FONTS_PATH = '/api/map/fonts/{fontstack}/{range}.pbf'
export const SPRITES_PATH = '/api/map/sprites'

/** 1234567 -> "1.2 MB". Decimal units, as the download tool uses. */
export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`
  const units = ['kB', 'MB', 'GB', 'TB']
  let value = bytes / 1000
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit += 1
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`
}
