import { HttpResponse, http } from 'msw'
import * as device from './device'
import type { Address, Station } from '../api/types'
import { PLACES, type Place } from './fixtures'
import { stream } from './stream'

/* Stands in for the daemon.
 *
 * MSW intercepts at the network level through a Service Worker, so
 * the client does a real fetch to a real URL and reads real status
 * codes -- the same code path that runs against carlib. Mocked
 * responses show up in the browser's Network tab too, which a
 * fetch-patching mock cannot give you.
 *
 * Delays are deliberate. A band sweep really does take seconds, and a
 * screen built against instant responses hides every place that needs
 * a pending state.
 */

/** A sweep, plus a few seconds per station to read each name. */
const SCAN_MS = 4200

/** Enough to see a spinner, not enough to be tiresome. */
const NORMAL_MS = 120

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function body<T>(request: Request): Promise<T> {
  try {
    return (await request.json()) as T
  } catch {
    return {} as T
  }
}

/** A fixture as the geocoder would return it. */
function asAddress(place: Place): Address {
  const parts = [
    place.name || [place.road, place.house_number].filter(Boolean).join(' '),
    place.postcode,
    place.city,
    place.county,
    'Sverige',
  ].filter(Boolean)

  return {
    display_name: parts.join(', '),
    latitude: place.latitude,
    longitude: place.longitude,
    name: place.name,
    house_number: place.house_number ?? '',
    road: place.road ?? '',
    neighbourhood: '',
    suburb: '',
    postcode: place.postcode ?? '',
    city: place.city,
    municipality: '',
    county: place.county,
    state: place.county,
    country: 'Sverige',
    country_code: 'SE',
    category: 'place',
    kind: place.kind,
    osm_id: String(Math.abs(hash(place.city + place.name + (place.road ?? '')))),
  }
}

/* Matched loosely and case-insensitively, on every word of the query
   independently. Real geocoders are far cleverer, but the point here
   is a list that narrows as you type, which this does. */
function matching(query: string): Place[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return []

  return PLACES.filter((place) => {
    const haystack = [
      place.name,
      place.road,
      place.house_number,
      place.postcode,
      place.city,
      place.county,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()

    return words.every((word) => haystack.includes(word))
  })
}

function hash(text: string): number {
  let value = 0
  for (const character of text) {
    value = (value * 31 + character.charCodeAt(0)) | 0
  }
  return value
}

export const handlers = [
  stream,

  http.get('/api/geocode/suggest', async ({ request }) => {
    const url = new URL(request.url)
    const query = url.searchParams.get('q') ?? ''
    const limit = Number(url.searchParams.get('limit') ?? 6)

    /* Short queries answer empty rather than everything, which is
       what the daemon does -- two characters match half the country
       and a request for them is wasted. */
    if (query.trim().length < 3) return HttpResponse.json([])

    /* Quicker than the other endpoints: this one runs on every
       keystroke, and a search that lags behind the typing feels
       broken however fast the results are. */
    await wait(160)
    return HttpResponse.json(matching(query).slice(0, limit).map(asAddress))
  }),

  http.get('/api/geocode/search', async ({ request }) => {
    const url = new URL(request.url)
    const query = url.searchParams.get('q') ?? ''
    const limit = Number(url.searchParams.get('limit') ?? 5)
    await wait(NORMAL_MS)
    return HttpResponse.json(matching(query).slice(0, limit).map(asAddress))
  }),

  http.get('/api/health', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json({ ok: true, state: 'memory' })
  }),

  http.get('/api/fm', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json(device.state())
  }),

  http.post('/api/fm/play', async ({ request }) => {
    const { station } = await body<{ station?: string | null }>(request)
    await wait(NORMAL_MS)

    if (station === null || station === undefined || station === '') {
      return HttpResponse.json(device.resume())
    }

    const named = device.byName(String(station))
    return HttpResponse.json(device.tune(named ?? Number(station)))
  }),

  http.post('/api/fm/pause', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json(device.setPaused(true))
  }),

  http.post('/api/fm/toggle', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json(device.setPaused(!device.state().paused))
  }),

  http.post('/api/fm/stop', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json(device.stop())
  }),

  http.post('/api/fm/tune', async ({ request }) => {
    const { offset = 0 } = await body<{ offset?: number }>(request)
    await wait(NORMAL_MS)
    return HttpResponse.json(
      device.tune((device.state().frequency ?? 87.5) + offset),
    )
  }),

  http.post('/api/fm/seek', async ({ request }) => {
    const { direction = 1 } = await body<{ direction?: number }>(request)
    await wait(NORMAL_MS)
    return HttpResponse.json(device.seekFrom(direction))
  }),

  http.get('/api/fm/presets', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json(device.allPresets())
  }),

  http.post('/api/fm/presets', async ({ request }) => {
    const { frequency, name = '' } =
      await body<{ frequency: number; name?: string }>(request)
    await wait(NORMAL_MS)
    return HttpResponse.json(device.savePreset(frequency, name))
  }),

  http.put('/api/fm/presets/order', async ({ request }) => {
    const { presets = [] } = await body<{ presets: Station[] }>(request)
    await wait(NORMAL_MS)
    return HttpResponse.json(device.reorderPresets(presets))
  }),

  http.delete('/api/fm/presets/:frequency', async ({ params }) => {
    await wait(NORMAL_MS)
    return HttpResponse.json(
      device.forgetPreset(Number(params.frequency)),
    )
  }),

  http.get('/api/fm/signals', async () => {
    await wait(NORMAL_MS)
    return HttpResponse.json(device.signals())
  }),

  http.post('/api/fm/scan', async ({ request }) => {
    const { identify = true } = await body<{ identify?: boolean }>(request)
    await wait(SCAN_MS)
    return HttpResponse.json(device.runScan(identify))
  }),
]

/** Answer the next call to a path with a failure, to see how a screen
 *  copes. Pass to `worker.use()`. */
export const failing = (
  method: 'get' | 'post' | 'delete',
  path: string,
  status = 503,
) =>
  http[method](
    path,
    () =>
      HttpResponse.json(
        {
          error: 'rtl_fm not found',
          type: 'NotAvailableError',
          hint: 'pacman -S rtl-sdr',
        },
        { status },
      ),
    { once: true },
  )
