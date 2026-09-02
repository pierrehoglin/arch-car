import type { Theme } from './types'

// The design picks a *contrast-adjusted* variant of the chosen swatch color
// per theme — e.g. blue's canonical swatch hex (#1d4e91) is already the
// light-theme variant, but needs to brighten to #5f96e0 to stay legible on
// the dark theme's near-black background, and vice versa for the others.
// These tables are taken directly from the design's own accentFor() logic.
const NIGHT_VARIANTS: Record<string, string> = {
  '#d8b146': '#d8b146',
  '#1d4e91': '#5f96e0',
  '#b21f2d': '#e0555f',
  '#7fe0a8': '#7fe0a8',
}
const DAY_VARIANTS: Record<string, string> = {
  '#d8b146': '#8a6d15',
  '#1d4e91': '#1d4e91',
  '#b21f2d': '#a01423',
  '#7fe0a8': '#157a43',
}

/**
 * Resolve a chosen ambient accent color to its theme-appropriate contrast
 * variant. Falls back to the base color unchanged for any accent not in the
 * table (e.g. a value from an older/different swatch set).
 */
export function accentFor(base: string, theme: Theme): string {
  const table = theme === 'day' ? DAY_VARIANTS : NIGHT_VARIANTS
  return table[base] ?? base
}

