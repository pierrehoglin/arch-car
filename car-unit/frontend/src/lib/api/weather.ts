import { request } from './client'
import type { Forecast } from './types'

/* Weather.
 *
 * The daemon caches per location and honours the provider's Expires
 * header, so asking often is cheap -- but `refresh` bypasses that,
 * which is what the button in the dialog is for.
 */

export const forecast = (place?: string, refresh = false) =>
  request<Forecast>('/weather', {
    query: { place, refresh: refresh || undefined },
    /* MET can take a moment when the cache is cold and the link is
       cellular. */
    timeout: 20_000,
  })
