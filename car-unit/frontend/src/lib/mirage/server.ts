import { createServer, Response, type Server } from 'miragejs'
import type { RadioState, Signal, Station } from '../api/types'
import { BROADCASTS, INITIAL, PRESETS, stateFor } from './fixtures'

/* A stand-in daemon, intercepting fetch.
 *
 * Mirage rather than a mock branch inside the API client: the client
 * then does a real fetch to a real URL with real status codes, so the
 * code that runs in development is the code that runs against the
 * daemon. A hand-written mock has to be kept in step with the client
 * by hand, and the first time it drifts is the first time a screen
 * works in development and not on the unit.
 *
 * Delays are deliberate. A band sweep really does take seconds, and a
 * screen built against instant responses hides every place that needs
 * a pending state.
 */

/** How long after tuning before RDS has decoded a name. */
const RDS_DELAY = 2500

/** A sweep, then a few seconds per station to read each name. */
const SCAN_MS = 4200

const BAND_MIN = 87.5
const BAND_MAX = 108.0

let server: Server | undefined

export function makeServer(): Server {
  if (server) return server

  let radio: RadioState = INITIAL
  let tunedAt = 0
  let presets: Station[] = [...PRESETS]
  let scanned: Signal[] = []

  /* Whether enough time has passed since tuning for RDS to have
     arrived. Computed on read rather than scheduled with a timer, so
     it stays right however long a screen waits before polling. */
  const decoded = () => Date.now() - tunedAt > RDS_DELAY

  const tune = (frequency: number): RadioState => {
    const clamped = Math.min(BAND_MAX, Math.max(BAND_MIN, frequency))
    tunedAt = Date.now()
    radio = stateFor(Math.round(clamped * 10) / 10, false)
    return radio
  }

  const current = (): RadioState =>
    radio.frequency === null
      ? radio
      : { ...stateFor(radio.frequency, decoded()), paused: radio.paused,
          playing: radio.playing }

  server = createServer({
    environment: 'development',
    logging: false,

    routes() {
      this.namespace = 'api'
      this.timing = 120

      this.get('/health', () => ({ ok: true, state: 'memory' }))

      this.get('/fm', () => current())

      this.post('/fm/play', (_schema, request) => {
        const body = JSON.parse(request.requestBody || '{}')
        const station = body.station
        if (station === null || station === undefined || station === '') {
          radio = { ...radio, playing: true, paused: false }
          return current()
        }
        const named = presets.find(
          (p) => p.name.toLowerCase() === String(station).toLowerCase(),
        )
        return tune(named ? named.frequency : Number(station))
      })

      this.post('/fm/pause', () => {
        radio = { ...current(), paused: true }
        return radio
      })

      this.post('/fm/toggle', () => {
        radio = { ...current(), paused: !radio.paused }
        return radio
      })

      this.post('/fm/stop', () => {
        radio = { ...radio, playing: false, paused: false, frequency: null }
        return radio
      })

      this.post('/fm/tune', (_schema, request) => {
        const { offset } = JSON.parse(request.requestBody || '{}')
        return tune((radio.frequency ?? BAND_MIN) + (offset ?? 0))
      })

      this.post('/fm/seek', (_schema, request) => {
        const { direction = 1 } = JSON.parse(request.requestBody || '{}')

        /* Seeking uses what a scan found, so before one has run there
           is nothing to seek between -- same as the daemon, which
           sweeps first if its cache is empty. */
        const known = (scanned.length ? scanned : BROADCASTS)
          .map((s) => s.frequency)
          .sort((a, b) => a - b)

        const here = radio.frequency ?? BAND_MIN
        const ordered = direction > 0 ? known : [...known].reverse()
        const next =
          ordered.find((f) =>
            direction > 0 ? f > here + 0.05 : f < here - 0.05,
          ) ?? ordered[0]

        return tune(next)
      })

      this.get('/fm/presets', () => presets)

      this.post('/fm/presets', (_schema, request) => {
        const { frequency, name } = JSON.parse(request.requestBody || '{}')
        presets = [
          ...presets.filter(
            (p) => Math.abs(p.frequency - frequency) > 0.01,
          ),
          { frequency, name: name || '' },
        ].sort((a, b) => a.frequency - b.frequency)
        return presets
      })

      this.delete('/fm/presets/:frequency', (_schema, request) => {
        const frequency = Number(request.params.frequency)
        presets = presets.filter(
          (p) => Math.abs(p.frequency - frequency) > 0.01,
        )
        return presets
      })

      this.get('/fm/signals', () => scanned)

      this.post(
        '/fm/scan',
        (_schema, request) => {
          const { identify = true } = JSON.parse(request.requestBody || '{}')

          scanned = BROADCASTS.map((b) => ({
            frequency: b.frequency,
            power: b.power,
            name: b.name,
            /* Without identify a sweep finds peaks but cannot name
               them: reading the name means tuning each one in turn. */
            rds_name: identify ? b.name : '',
            pi: identify ? b.pi : '',
          }))

          return scanned
        },
        { timing: SCAN_MS },
      )

      /* Anything unmatched goes to the network, so Vite's own
         requests are not swallowed. */
      this.passthrough()
      this.passthrough('http://localhost:**')
      this.passthrough('https://fonts.googleapis.com/**')
      this.passthrough('https://fonts.gstatic.com/**')
    },
  })

  return server
}

/** Fail the next request to a path, to see how a screen copes. */
export function breakOnce(method: string, path: string, status = 503): void {
  server?.[method.toLowerCase() as 'get'](
    `/api${path}`,
    () =>
      new Response(status, {}, {
        error: 'rtl_fm not found',
        type: 'NotAvailableError',
        hint: 'pacman -S rtl-sdr',
      }),
  )
}
