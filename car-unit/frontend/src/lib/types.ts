export type Theme = 'night' | 'day'

/** What actually lands on data-theme. Night Panel is a third value the
 *  DOM sees, though it is not a theme the user picks between. */
export type ThemeAttr = Theme | 'nightpanel'

export interface NavItem {
  href: string
  label: string
  icon: string
}

/** The rail, in order. Settings is separate: it sits at the bottom. */
export const NAV: NavItem[] = [
  { href: '/', label: 'Home', icon: 'home' },
  { href: '/media', label: 'Media', icon: 'media' },
  { href: '/map', label: 'Map', icon: 'map' },
  { href: '/phone', label: 'Phone', icon: 'phone' },
  { href: '/car', label: 'Car', icon: 'car' },
  { href: '/camera', label: 'Camera', icon: 'camera' },
]

/** Settings sections, in rail order. Each is a route so a link can
 *  point straight at one -- the Bluetooth badge goes to
 *  /settings/connectivity. */
export interface Section {
  href: string
  label: string
}

export const SETTINGS_SECTIONS: Section[] = [
  { href: '/settings/display', label: 'Display' },
  { href: '/settings/sound', label: 'Sound' },
  { href: '/settings/connectivity', label: 'Connectivity' },
  { href: '/settings/vehicle', label: 'Vehicle' },
  { href: '/settings/driver-assist', label: 'Driver Assist' },
  { href: '/settings/about', label: 'About' },
]

/** Only while developing. The route exists either way -- Vite would
 *  have to be told to drop it -- but nothing links to it in a build,
 *  and the module it controls is DEV-only anyway. */
export const DEV_SECTIONS: Section[] = [
  { href: '/settings/mocks', label: 'Mocks' },
]

/** Media sources, each its own route. FM and USB have controls that
 *  have nothing to do with a phone player -- a frequency dial against
 *  a track list -- so they are pages, not a switch inside one. */
/** A media source, and what the daemon calls it.
 *
 * `id` is the name in /api/media/{id}, so a source that starts
 * playing can be matched to the screen that shows it. FM has none:
 * it is the car's own radio, not a player the daemon polls.
 */
export interface MediaSource extends Section {
  id?: string
}

/* FM first: it is the one that always works, needs no phone, and is
   where the car lands when nothing else is playing.
   
   Spotify before Bluetooth so that when both report playing -- which
   they do when the phone is part of the same Connect session -- the
   more specific one wins. */
export const MEDIA_SOURCES: MediaSource[] = [
  { href: '/media/fm', label: 'FM' },
  { href: '/media/spotify', label: 'Spotify', id: 'spotify' },
  { href: '/media/bluetooth', label: 'Bluetooth', id: 'bluetooth' },
]

/** The four ambient colours. Stored as the canonical swatch hex;
 *  accentFor() resolves the per-theme contrast variant. */
export const SWATCHES = ['#d8b146', '#1d4e91', '#b21f2d', '#7fe0a8']

export const SWATCH_NAMES: Record<string, string> = {
  '#d8b146': 'Amber',
  '#1d4e91': 'Blue',
  '#b21f2d': 'Red',
  '#7fe0a8': 'Green',
}
