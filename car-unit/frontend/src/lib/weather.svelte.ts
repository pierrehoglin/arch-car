import * as api from './api/weather'
import { saved } from './api/places'
import { RequestFailed } from './api/client'
import { on } from './api/stream.svelte'
import { metresBetween } from './address'
import { located } from './position.svelte'
import {
  CURRENT_PLACE,
  type Condition,
  type Forecast,
  type Place,
  type Position,
} from './api/types'

/* The forecast, for the dashboard and the dialog.
 *
 * Two of them: the dashboard always shows where the car is, and the
 * dialog can look at a saved place without that changing the
 * dashboard. While the dialog is on the current position they are
 * the same forecast, fetched once.
 *
 * Fetched rather than streamed: it changes on the hour, not on the
 * second, and the daemon already caches it per location and honours
 * the provider's Expires header. A place on the event stream would
 * carry the same payload over and over.
 */

/** Often enough to follow the hour, rarely enough to be free. */
const REFRESH_MS = 10 * 60 * 1000

/** The daemon caches forecasts per kilometre square, so past this the
 *  car is under another one -- worth asking for without waiting for
 *  the next ten-minute refresh. */
const MOVED_METRES = 1000

/** After a failed load, before moving may prompt another. Without it,
 *  no signal would mean a retry on every position update -- once a
 *  second while driving. A successful load needs no pause: the next
 *  one waits for another kilometre anyway. */
const RETRY_MS = 60 * 1000

interface Store {
  /** Where the car is. What the dashboard shows, always -- whatever
   *  the dialog is looking at. */
  here: Forecast | null

  /** What the forecast dialog shows: `here` while it is on the
   *  current position, a saved place's forecast otherwise. */
  forecast: Forecast | null
  /** For the dialog's selection, not for `here` refreshing in the
   *  background. */
  loading: boolean
  error: string
  /** When we last heard from the daemon, not when the provider last
   *  issued it -- that is `forecast.updated`. */
  fetched: number | null

  /** Which place the dialog is showing. */
  place: string
  /** Saved places, for the picker. */
  places: Place[]
}

export const weather = $state<Store>({
  here: null,
  forecast: null,
  loading: false,
  error: '',
  fetched: null,
  place: CURRENT_PLACE,
  places: [],
})

/* Control flow, deliberately not reactive.

   watch() runs inside an $effect, and anything it reads from the
   store becomes a dependency of that effect -- finishing a load would
   invalidate it, which would load again, for ever. So the guards and
   the selection are plain mirrors here; the store's fields are for
   showing, these are for deciding. */
let hereLoading = false
let selected = CURRENT_PLACE
/** Where the forecast on the dashboard is for, and when it was last
 *  asked for -- for deciding whether a move is worth a new one. */
let hereAt: [number, number] | null = null
let hereFailed = 0
/** Bumped per request for a saved place, so a slow answer for a
 *  place already left is dropped rather than shown. */
let ticket = 0

function message(cause: unknown): string {
  return cause instanceof RequestFailed || cause instanceof Error
    ? cause.message
    : String(cause)
}

/** The current position's forecast, for the dashboard -- and for the
 *  dialog when it is showing the current position too. */
async function loadHere(refresh = false): Promise<void> {
  /* Overlapping loads would race to set the same field, and the
     slower one would win. */
  if (hereLoading) return
  hereLoading = true

  const forDialog = () => selected === CURRENT_PLACE
  if (forDialog()) weather.loading = true

  try {
    const found = await api.forecast(CURRENT_PLACE, refresh)
    weather.here = found
    hereAt = [found.latitude, found.longitude]
    hereFailed = 0
    if (forDialog()) {
      weather.forecast = found
      weather.fetched = Date.now()
      weather.error = ''
    }
  } catch (cause) {
    hereFailed = Date.now()
    if (forDialog()) weather.error = message(cause)
  } finally {
    hereLoading = false
    if (forDialog()) weather.loading = false
  }
}

/** A saved place's forecast, for the dialog only. */
async function loadPlace(place: string, refresh = false): Promise<void> {
  const mine = ++ticket
  weather.loading = true
  try {
    const found = await api.forecast(place, refresh)
    if (mine === ticket && selected === place) {
      weather.forecast = found
      weather.fetched = Date.now()
      weather.error = ''
    }
  } catch (cause) {
    if (mine === ticket) weather.error = message(cause)
  } finally {
    if (mine === ticket) weather.loading = false
  }
}

/** What the dialog is showing, again. `refresh` skips the daemon's
 *  cache -- the dialog's Refresh button. */
export async function load(refresh = false): Promise<void> {
  if (selected === CURRENT_PLACE) return loadHere(refresh)
  return loadPlace(selected, refresh)
}

/**
 * Show somewhere else in the dialog.
 *
 * The dashboard is not affected: it always shows where the car is,
 * so it can never be showing a saved place's weather under a heading
 * that looks like the current one.
 *
 * The old forecast stays up while the new one is fetched. Clearing it
 * collapses the dialog to a spinner and back, which for a request
 * that takes a moment is more disruptive than the wait -- see the
 * dimming and the spinner in the dialog.
 */
export async function choose(place: string): Promise<void> {
  if (place === selected) return
  selected = place
  weather.place = place
  weather.error = ''

  if (place === CURRENT_PLACE) {
    /* Already here from the dashboard's refreshes; nothing to fetch
       unless it has not arrived yet. */
    ticket++
    weather.loading = false
    if (weather.here) {
      weather.forecast = weather.here
      return
    }
  }
  await load()
}

/**
 * Saved places, fetched every time the picker is shown.
 *
 * Not once and kept: places are added and removed in Settings, and a
 * list held from the first opening never heard about them. It is a
 * small local request, made when someone opens the forecast.
 *
 * A place that has gone while it was selected -- forgotten in
 * Settings -- puts the forecast back on the current position rather
 * than leaving a selection the daemon can no longer resolve.
 */
export async function loadPlaces(): Promise<void> {
  try {
    const places = await saved()
    weather.places = places

    const selected = weather.place
    const known =
      selected === CURRENT_PLACE ||
      places.some((place) => place.name === selected)
    if (!known) await choose(CURRENT_PLACE)
  } catch {
    // The picker falls back to the current position, which needs no
    // list.
  }
}

/**
 * Keep the current position's forecast fresh while a screen is
 * mounted: every ten minutes, and sooner once the car has driven
 * out of the square the forecast was for.
 *
 * Returns a stop function, so an $effect can hand it back.
 */
export function watch(interval = REFRESH_MS): () => void {
  loadHere()
  const timer = setInterval(() => loadHere(), interval)

  const stop = on('position', (data) => {
    const reading = data as Position
    if (!located(reading) || !hereAt) return
    if (Date.now() - hereFailed < RETRY_MS) return
    const moved = metresBetween(
      hereAt[0],
      hereAt[1],
      reading.latitude,
      reading.longitude,
    )
    if (moved > MOVED_METRES) loadHere()
  })

  return () => {
    clearInterval(timer)
    stop()
  }
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
