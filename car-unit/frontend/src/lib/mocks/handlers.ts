import { HttpResponse, http } from 'msw'
import * as device from './device'
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

export const handlers = [
  stream,

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
