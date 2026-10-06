import { reverse } from './api/places'
import type { Address, Place } from './api/types'

/* The pin on the map: somewhere chosen to go, or just to look at.

   Kept here rather than in the map screen, so it is still there after
   a look at the home screen or Settings -- the screen is rebuilt each
   time it opens, and anything it held would go with it. Not saved
   anywhere: a restart clears it, as it should for something chosen
   for the drive at hand.

   Three ways in, one shape out: a search result, a saved place, or a
   point tapped on the map, whose address is then looked up. */

export type PinSource = 'search' | 'saved' | 'map'

export interface Pin {
  latitude: number
  longitude: number
  /** First line: a name, or the street. Empty while a tapped point's
   *  address is being looked up. */
  title: string
  /** Second line: postcode and town, minus anything the title said. */
  subtitle: string
  /** What goes in the search field for it. */
  label: string
  source: PinSource
  /** A tapped point whose address has not arrived yet. */
  looking: boolean
}

export const destination = $state<{ pin: Pin | null }>({ pin: null })

/* Bumped for every pin placed, so a slow lookup for a point the pin
   has since left is dropped rather than written over the new one. */
let ticket = 0

const capital = (text: string) =>
  text ? text[0].toUpperCase() + text.slice(1) : text

/** The parts of an address as two lines: what it is, then postcode
 *  and town. The same split the dashboard uses. */
function lines(found: Address): [string, string] {
  const street = [found.road, found.house_number].filter(Boolean).join(' ')
  const town = found.city || found.municipality || found.suburb || found.county
  const postal = [found.postcode, town].filter(Boolean).join(' ')

  const title = found.name || street
  if (!title) return [postal || found.display_name.split(', ')[0] || '', '']
  return [title, postal]
}

/** A search suggestion, chosen. */
export function fromSearch(found: Address): void {
  ticket++
  const [title, subtitle] = lines(found)
  destination.pin = {
    latitude: found.latitude,
    longitude: found.longitude,
    title,
    subtitle,
    label: [title, subtitle.replace(/^\d{3} ?\d{2} /, '')]
      .filter(Boolean)
      .join(', '),
    source: 'search',
    looking: false,
  }
}

/** A saved place, chosen. Named as it was saved, with the address it
 *  was saved with underneath. */
export function fromSaved(place: Place): void {
  ticket++
  const name = capital(place.name)
  destination.pin = {
    latitude: place.latitude,
    longitude: place.longitude,
    title: name,
    subtitle: place.address,
    label: name,
    source: 'saved',
    looking: false,
  }
}

/**
 * A point placed by hand -- tapped, or the pin dragged there.
 *
 * Placed at once, with its address following when it arrives. Without
 * signal it stays a point: the coordinates are shown instead, and the
 * pin works the same either way.
 */
export async function dropAt(latitude: number, longitude: number): Promise<void> {
  const mine = ++ticket
  const where = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`
  destination.pin = {
    latitude,
    longitude,
    title: '',
    subtitle: '',
    label: where,
    source: 'map',
    looking: true,
  }

  try {
    const found = await reverse(latitude, longitude)
    if (mine !== ticket || !destination.pin) return
    const [title, subtitle] = lines(found)
    destination.pin = {
      ...destination.pin,
      title: title || where,
      subtitle,
      label: title || where,
      looking: false,
    }
  } catch {
    if (mine !== ticket || !destination.pin) return
    destination.pin = { ...destination.pin, title: where, looking: false }
  }
}

export function clear(): void {
  ticket++
  destination.pin = null
}
