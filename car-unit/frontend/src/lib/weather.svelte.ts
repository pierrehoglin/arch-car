import * as api from './api/weather'
import { saved } from './api/places'
import { RequestFailed } from './api/client'
import { CURRENT_PLACE, type Condition, type Forecast, type Place } from './api/types'

/* The forecast, shared between the dashboard and the dialog.
 *
 * Fetched rather than streamed: it changes on the hour, not on the
 * second, and the daemon already caches it per location and honours
 * the provider's Expires header. A place on the event stream would
 * carry the same payload over and over.
 */

/** Often enough to follow the hour, rarely enough to be free. */
const REFRESH_MS = 10 * 60 * 1000

interface Store {
  forecast: Forecast | null
  loading: boolean
  error: string
  /** When we last heard from the daemon, not when the provider last
   *  issued it -- that is `forecast.updated`. */
  fetched: number | null

  /** Which place the forecast is for. */
  place: string
  /** Saved places, for the picker. */
  places: Place[]
}

export const weather = $state<Store>({
  forecast: null,
  loading: false,
  error: '',
  fetched: null,
  place: CURRENT_PLACE,
  places: [],
})

/* The guard, deliberately not reactive.
 *
 * Reading weather.loading here would make every $effect that calls
 * load() depend on it -- so finishing a load would invalidate the
 * effect, which would call load() again, for ever. The flag on the
 * store is for showing a spinner; this one is control flow, and the
 * two want different things.
 */
let loading = false

export async function load(refresh = false): Promise<void> {
  /* Overlapping loads would race to set the same field, and the
     slower one would win. */
  if (loading) return

  loading = true
  weather.loading = true
  try {
    weather.forecast = await api.forecast(weather.place, refresh)
    weather.fetched = Date.now()
    weather.error = ''
  } catch (cause) {
    weather.error =
      cause instanceof RequestFailed || cause instanceof Error
        ? cause.message
        : String(cause)
  } finally {
    loading = false
    weather.loading = false
  }
}

/**
 * Look somewhere else.
 *
 * One selection, shared: the dialog is showing the forecast the
 * dashboard summarises, so having them disagree would mean two
 * forecasts on screen for two different places with nothing saying
 * which was which. The dashboard names the place it is showing.
 */
export async function choose(place: string): Promise<void> {
  if (place === weather.place) return
  weather.place = place

  /* The old forecast stays up while the new one is fetched. Clearing
     it collapses the dialog to a spinner and back, which for a
     request that takes a moment is more disruptive than the wait.
     
     Showing readings for the place you have just left is only
     acceptable while it is visibly pending -- see the dimming and the
     spinner in the dialog -- and `forecast.place` keeps naming the
     one on screen rather than the one selected. */
  await load()
}

/** Saved places, fetched once. */
export async function loadPlaces(): Promise<void> {
  if (weather.places.length) return
  try {
    weather.places = await saved()
  } catch {
    // The picker falls back to the current position, which needs no
    // list.
  }
}

/**
 * Keep it current while a screen is mounted.
 *
 * Returns a stop function, so an $effect can hand it back.
 */
export function watch(interval = REFRESH_MS): () => void {
  load()
  const timer = setInterval(() => load(), interval)
  return () => clearInterval(timer)
}

/* Note for anyone adding to this file: nothing reachable from watch()
   may read a $state field. An $effect calling it would then re-run
   whenever that field changed, and since watch() starts a load which
   changes fields, it would never settle. */


/* Conditions to icons, in one place: the dashboard, the dialog's
   current block and both of its lists all need the same mapping, and
   four copies would drift the first time one was adjusted.

   Sleet takes the snow icon rather than rain. Tabler has no sleet,
   and of the two it is the one that changes how you drive. */
const ICONS: Record<Condition, string> = {
  clear: 'sun',
  'partly-cloudy': 'cloud',
  cloudy: 'cloud',
  fog: 'cloud-fog',
  drizzle: 'droplet',
  rain: 'cloud-rain',
  sleet: 'cloud-snow',
  snow: 'cloud-snow',
  thunder: 'cloud-storm',
  unknown: 'cloud',
}

export const iconFor = (condition: Condition) =>
  ICONS[condition] ?? 'cloud'

/* Read out as a sentence rather than a slug. The API sends
   'partly-cloudy'; nobody wants to see that. */
const NAMES: Record<Condition, string> = {
  clear: 'Clear',
  'partly-cloudy': 'Partly cloudy',
  cloudy: 'Overcast clouds',
  fog: 'Fog',
  drizzle: 'Drizzle',
  rain: 'Rain',
  sleet: 'Sleet',
  snow: 'Snow',
  thunder: 'Thunderstorm',
  unknown: '',
}

export const nameFor = (condition: Condition) => NAMES[condition] ?? ''
