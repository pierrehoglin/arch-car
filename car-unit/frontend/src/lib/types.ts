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

/** The four ambient colours. Stored as the canonical swatch hex;
 *  accentFor() resolves the per-theme contrast variant. */
export const SWATCHES = ['#d8b146', '#1d4e91', '#b21f2d', '#7fe0a8']

export const SWATCH_NAMES: Record<string, string> = {
  '#d8b146': 'Amber',
  '#1d4e91': 'Blue',
  '#b21f2d': 'Red',
  '#7fe0a8': 'Green',
}
