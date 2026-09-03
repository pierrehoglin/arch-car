import { accentFor } from './accent'
import type { Theme, ThemeAttr } from './types'

/* Display preferences.
 *
 * Nothing here is wired to the daemon yet. The values live for the
 * session and reset on reload, which is the right shape while the
 * screens are being built -- there is no half-persisted state to
 * reason about, and no backend contract to unpick later.
 */

interface Display {
  theme: Theme
  /** Dims everything except the speedometer.
   *
   *  Not a stored setting. On a real 9-5 this is a switch on the
   *  dashboard, so if it is ever more than a UI toggle it will arrive
   *  over CAN rather than out of a config file. */
  nightPanel: boolean
  ambient: string
  brightness: number
  volume: number
  /** Silences output without losing the level, so unmuting comes back
   *  where it was rather than at zero. */
  muted: boolean
  panel: boolean
}

export const display = $state<Display>({
  theme: 'night',
  nightPanel: false,
  ambient: '#d8b146',
  brightness: 72,
  volume: 60,
  muted: false,
  panel: true,
})

/** What goes on data-theme. Night Panel is a global override: when it
 *  is on it wins whichever theme is underneath. */
export function themeAttr(): ThemeAttr {
  return display.nightPanel ? 'nightpanel' : display.theme
}

/** The accent, contrast-corrected for the theme.
 *
 *  Night Panel deliberately leaves --accent unset in CSS so the chosen
 *  ambient colour still comes through, which is why this resolves
 *  against the theme underneath rather than against the attribute. */
export function accent(): string {
  return accentFor(display.ambient, display.theme)
}
