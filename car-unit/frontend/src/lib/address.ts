import type { Address } from './api/types'

/* Telling search results apart.
 *
 * One address is often several OpenStreetMap objects: the address
 * point, the building outline carrying the same address, and a shop
 * or office inside it. They come back as separate results with the
 * same street and number, and the difference is in what each object
 * is, where exactly it sits, and occasionally its postcode -- which is
 * what these say. */

const capital = (text: string) =>
  text ? text[0].toUpperCase() + text.slice(1) : text

const words = (text: string) => text.replace(/_/g, ' ')

/** Settlements and areas, named as themselves. */
const AREAS = new Set([
  'city', 'town', 'village', 'hamlet', 'suburb', 'quarter',
  'neighbourhood', 'locality', 'isolated_dwelling', 'farm', 'municipality',
  'county', 'state', 'country', 'island',
])

/** Kinds of business or facility, named by what they are. */
const FACILITIES = new Set([
  'amenity', 'shop', 'tourism', 'leisure', 'office', 'craft', 'healthcare',
  'sport', 'historic', 'man_made', 'railway', 'aeroway', 'public_transport',
])

/**
 * What the object is, in a word or two: "Address", "Building
 * (apartments)", "Shop: supermarket", "Street", "Town".
 */
export function kindOf(found: Address): string {
  const key = found.category
  const value = found.kind

  if (!key) return ''
  if (key === 'place' && value === 'house') return 'Address'
  if (key === 'place' && AREAS.has(value)) return capital(words(value))
  if (key === 'building') {
    return value && value !== 'yes'
      ? `Building (${words(value)})`
      : 'Building'
  }
  if (key === 'highway') return 'Street'
  if (key === 'boundary') return 'Area'
  if (FACILITIES.has(key)) {
    return value && value !== 'yes'
      ? `${capital(words(key))}: ${words(value)}`
      : capital(words(key))
  }
  return capital(words(value || key))
}

/** Great-circle distance in metres. */
export function metresBetween(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const r = 6_371_000
  const rad = Math.PI / 180
  const dLat = (lat2 - lat1) * rad
  const dLon = (lon2 - lon1) * rad
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2
  return 2 * r * Math.asin(Math.sqrt(a))
}

/** "350 m away", "12 km away". */
export function distanceLabel(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m away`
  if (metres < 10_000) return `${(metres / 1000).toFixed(1)} km away`
  return `${Math.round(metres / 1000)} km away`
}

/**
 * The line that tells one result from another: what it is, which
 * district and postcode, and how far from the car.
 */
export function distinguish(
  found: Address,
  from: { latitude: number; longitude: number } | null,
): string {
  const parts = [kindOf(found), found.suburb, found.postcode]
  if (from) {
    parts.push(
      distanceLabel(
        metresBetween(
          from.latitude,
          from.longitude,
          found.latitude,
          found.longitude,
        ),
      ),
    )
  }
  return parts.filter(Boolean).join(' · ')
}
