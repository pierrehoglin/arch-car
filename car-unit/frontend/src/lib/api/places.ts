import { request } from './client'
import type { Address, Place } from './types'

/* Geocoding.
 *
 * Suggestions come from Photon, which is built for search-as-you-type;
 * Nominatim forbids autocomplete outright. Both are rate limited, so
 * the caller debounces -- see the map screen.
 */

/** Below this a query matches half the country. */
export const MIN_CHARS = 3

export const suggest = (query: string, limit = 6) =>
  request<Address[]>('/geocode/suggest', {
    query: { q: query, limit },
  })

export const search = (query: string, limit = 5) =>
  request<Address[]>('/geocode/search', {
    query: { q: query, limit },
  })

/** Places that have been saved, by name. */
export const saved = () => request<Place[]>('/places')

/** Where the car is, as the geocoder last recorded it. Null before
 *  the first GPS fix. */
export const current = () => request<Place | null>('/places/current')

/** Remove a saved place. Answers with the places that are left. */
export const forget = (name: string) =>
  request<Place[]>(`/places/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
