import * as api from './api/settings'
import { accentFor } from './accent'
import type { Theme, ThemeAttr } from './types'

/* Display preferences.
 *
 * Volume and mute used to live here and do not any more: they are
 * the state of a device, not a preference, and they belong to the
 * audio store which the daemon feeds.
 *
 * The theme and the accent are stored by the daemon, under `ui.theme`
 * and `ui.ambient`. Night Panel is not: it is a switch rather than a
 * preference.
 */

/** Keys the daemon holds for this store. */
const THEME = 'ui.theme'
const AMBIENT = 'ui.ambient'

interface Display {
  theme: Theme
  /** Dims everything except the speedometer.
   *
   *  Not a stored setting. On a real 9-5 this is a switch on the
   *  dashboard, so if it is ever more than a UI toggle it will arrive
   *  over CAN rather than out of a config file. */
  nightPanel: boolean
  ambient: string
}

export const display = $state<Display>({
  theme: 'night',
  nightPanel: false,
  ambient: '#d8b146',
})

/* Until the stored values have arrived. Writing before then would
   save the defaults over whatever is on disk -- the screens render
   immediately, and a theme applied on the way past is still a
   change as far as a naive save is concerned. */
let loaded = false

/**
 * Take the stored preferences.
 *
 * Called once, from the root layout. A value that is missing or not
 * one of the two themes leaves the default alone rather than
 * applying something the CSS has no palette for.
 */
export async function load(): Promise<void> {
  try {
    const stored = await api.all()

    const theme = api.valueAt(stored, THEME)
    if (theme === 'night' || theme === 'day') display.theme = theme

    const ambient = api.valueAt(stored, AMBIENT)
    if (typeof ambient === 'string' && /^#[0-9a-f]{6}$/i.test(ambient)) {
      display.ambient = ambient
    }
  } catch {
    /* No daemon, or it has no opinion. The defaults are already in
       place and the screens work; a car that cannot reach its own
       settings should still show something. */
  } finally {
    loaded = true
  }
}

/* One write per change, not per keystroke. Picking through the
   swatches is several changes in a second, and each one is a file
   written on a memory card. */
let pending: ReturnType<typeof setTimeout> | undefined

function save(values: Record<string, unknown>): void {
  if (!loaded) return

  clearTimeout(pending)
  pending = setTimeout(() => {
    api.update(values).catch(() => {
      /* Nothing to do about it here. The screen already shows the
         choice; it will simply not survive a reload, and the next
         change tries again. */
    })
  }, 400)
}

/** Choose a palette. */
export function setTheme(theme: Theme): void {
  display.theme = theme
  save({ [THEME]: theme })
}

/** Choose the accent. */
export function setAmbient(swatch: string): void {
  display.ambient = swatch
  save({ [AMBIENT]: swatch })
}

/** What goes on data-theme. Night Panel is a global override: when it
 *  is on it wins whichever theme is underneath. */
export function themeAttr(): ThemeAttr {
  return display.nightPanel ? 'nightpanel' : display.theme
}

/** Whether the panel is dark.
 *
 *  Night Panel is darker than night, so the only light theme is day.
 *  Written against the attribute rather than the theme so a fourth
 *  theme cannot be added without this being looked at. */
export const isDark = (): boolean => themeAttr() !== 'day'

/** The accent, contrast-corrected for the theme.
 *
 *  Night Panel deliberately leaves --accent unset in CSS so the chosen
 *  ambient colour still comes through, which is why this resolves
 *  against the theme underneath rather than against the attribute. */
export function accent(): string {
  return accentFor(display.ambient, display.theme)
}
