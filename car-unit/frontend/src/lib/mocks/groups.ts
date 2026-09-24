/* Which part of the API a route belongs to.
 *
 * Mocking is per group rather than all at once, because the daemon
 * gains routes one area at a time -- audio may be live while weather
 * is not, and switching everything over to find out would mean
 * losing the screens that have nothing behind them yet.
 */

export interface Group {
  id: string
  label: string
  detail: string
  /** Route prefixes, matched in the order the groups are listed. */
  paths: string[]
}

export const GROUPS: Group[] = [
  {
    id: 'audio',
    label: 'Audio',
    detail: 'Volume and mute',
    paths: ['/api/audio'],
  },
  {
    id: 'bluetooth',
    label: 'Bluetooth',
    detail: 'The service, pairing and devices',
    paths: ['/api/bluetooth'],
  },
  {
    id: 'events',
    label: 'Events',
    detail: 'The stream that pushes changes',
    paths: ['/api/events'],
  },
  {
    id: 'fm',
    label: 'Radio',
    detail: 'Tuning, presets and scanning',
    paths: ['/api/fm'],
  },
  {
    id: 'media',
    label: 'Media',
    detail: 'What Bluetooth and Spotify are playing',
    paths: ['/api/media'],
  },
  {
    id: 'weather',
    label: 'Weather',
    detail: 'Current conditions and the forecast',
    paths: ['/api/weather'],
  },
  {
    id: 'places',
    label: 'Places',
    detail: 'Saved locations and address search',
    paths: ['/api/places', '/api/geocode'],
  },
  {
    id: 'other',
    label: 'Everything else',
    detail: 'Health, and anything not listed above',
    paths: ['/api/'],
  },
]

/** Which group a path falls in. The last group catches the rest. */
export function groupOf(path: string): string {
  for (const group of GROUPS) {
    if (group.paths.some((prefix) => path.startsWith(prefix))) {
      return group.id
    }
  }
  return 'other'
}
