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

/** The address at a point. Cached by the daemon to about a city
 *  block, and a request someone made by placing a pin -- which the
 *  Nominatim policy permits. */
export const reverse = (latitude: number, longitude: number) =>
  request<Address>('/geocode/reverse', {
    query: { lat: latitude, lon: longitude },
  })

/** Places that have been saved, by name. */
export const saved = () => request<Place[]>('/places')

/** Where the car is, as the geocoder last recorded it. Null before
 *  the first GPS fix. */
export const current = () => request<Place | null>('/places/current')

export interface NewPlace {
  name: string
  /** Omitted, the daemon saves where the car is now. */
  latitude?: number
  longitude?: number
  address?: string
  /** Look the address up. Off when one is given already. */
  lookup?: boolean
}

/** Save a place, or move one: the name is the key. Answers with
 *  every saved place. */
export const save = (place: NewPlace) =>
  request<Place[]>('/places', { method: 'POST', body: place })

/** Remove a saved place. Answers with the places that are left. */
export const forget = (name: string) =>
  request<Place[]>(`/places/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
