import { request } from './client'
import type { RadioState, Signal, Station } from './types'

/* The FM endpoints, one function each.
 *
 * Thin on purpose: no caching, no retries, no massaging of what comes
 * back. Anything cleverer belongs in the store, where it can be seen
 * alongside the state it is being clever about.
 */

/** Scanning sweeps the whole band, and identifying tunes each peak in
 *  turn to read its RDS name -- a few seconds per station. */
const SCAN_TIMEOUT = 120_000

export const status = () => request<RadioState>('/fm')

export const play = (station?: string | number) =>
  request<RadioState>('/fm/play', {
    method: 'POST',
    body: { station: station === undefined ? null : String(station) },
  })

export const pause = () =>
  request<RadioState>('/fm/pause', { method: 'POST' })

export const toggle = () =>
  request<RadioState>('/fm/toggle', { method: 'POST' })

export const stop = () => request<RadioState>('/fm/stop', { method: 'POST' })

/** Step the frequency. The backend clamps to the band. */
export const tune = (offset: number) =>
  request<RadioState>('/fm/tune', { method: 'POST', body: { offset } })

/** Jump to the next station a scan found, wrapping at the ends. */
export const seek = (direction: 1 | -1) =>
  request<RadioState>('/fm/seek', { method: 'POST', body: { direction } })

export const presets = () => request<Station[]>('/fm/presets')

export const savePreset = (frequency: number, name = '') =>
  request<Station[]>('/fm/presets', {
    method: 'POST',
    body: { frequency, name },
  })

export const forgetPreset = (frequency: number) =>
  request<Station[]>(`/fm/presets/${frequency}`, { method: 'DELETE' })

/** What the last scan found, without sweeping again. */
export const signals = () => request<Signal[]>('/fm/signals')

/**
 * Sweep the band.
 *
 * With identify, each peak is tuned in turn to read its RDS name --
 * slower, but it is the only reliable way to tell a real station from
 * a noise peak, since almost every broadcaster carries RDS.
 */
export const scan = (identify = true) =>
  request<Signal[]>('/fm/scan', {
    method: 'POST',
    body: { identify },
    timeout: SCAN_TIMEOUT,
  })
