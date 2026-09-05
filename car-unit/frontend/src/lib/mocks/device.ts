import type { RadioState, Signal, Station } from '../api/types'
import { BROADCASTS, INITIAL, PRESETS, stateFor } from './fixtures'

/* The simulated device.
 *
 * One place holding the state, so the REST handlers and the event
 * stream cannot disagree: a POST changes it here and the stream sees
 * the change, exactly as a command to the daemon and its supervisor
 * would.
 */

const BAND_MIN = 87.5
const BAND_MAX = 108.0

/** How long after tuning before RDS has decoded a name. */
const RDS_DELAY = 2500

type Listener = (event: string, data: unknown) => void

const listeners = new Set<Listener>()

let radio: RadioState = INITIAL
let presets: Station[] = [...PRESETS]
let scanned: Signal[] = []
let decodeTimer: ReturnType<typeof setTimeout> | undefined

function emit(event: string, data: unknown): void {
  for (const listener of listeners) listener(event, data)
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export const state = () => radio
export const allPresets = () => presets
export const signals = () => scanned

export function tune(frequency: number): RadioState {
  const clamped = Math.min(BAND_MAX, Math.max(BAND_MIN, frequency))
  radio = stateFor(Math.round(clamped * 10) / 10, false)
  emit('fm', radio)

  /* RDS arrives a couple of seconds later, as a second event rather
     than being folded into the first. That is what actually happens,
     and it is the case the screen has to hold its layout through. */
  clearTimeout(decodeTimer)
  decodeTimer = setTimeout(() => {
    if (radio.frequency === null) return
    radio = { ...stateFor(radio.frequency, true), paused: radio.paused }
    emit('fm', radio)
  }, RDS_DELAY)

  return radio
}

export function setPaused(paused: boolean): RadioState {
  radio = { ...radio, paused }
  emit('fm', radio)
  return radio
}

export function stop(): RadioState {
  clearTimeout(decodeTimer)
  radio = { ...radio, playing: false, paused: false, frequency: null }
  emit('fm', radio)
  return radio
}

export function resume(): RadioState {
  radio = { ...radio, playing: true, paused: false }
  emit('fm', radio)
  return radio
}

export function seekFrom(direction: number): RadioState {
  /* Seeking uses what a scan found. Before one has run there is
     nothing to seek between, so it falls back to the full list --
     the daemon sweeps first in that case. */
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
}

export function byName(name: string): number | null {
  const preset = presets.find(
    (p) => p.name.toLowerCase() === name.toLowerCase(),
  )
  return preset?.frequency ?? null
}

export function savePreset(frequency: number, name: string): Station[] {
  const at = presets.findIndex(
    (p) => Math.abs(p.frequency - frequency) < 0.01,
  )

  /* Order is the user's, so an existing preset keeps its place and a
     new one goes on the end. Sorting by frequency here -- which
     carlib currently does -- would throw away a reorder on the next
     rename. */
  if (at === -1) {
    presets = [...presets, { frequency, name }]
  } else {
    presets = presets.map((p, index) =>
      index === at ? { frequency, name } : p,
    )
  }

  emit('presets', presets)
  return presets
}

export function reorderPresets(next: Station[]): Station[] {
  presets = [...next]
  emit('presets', presets)
  return presets
}

export function forgetPreset(frequency: number): Station[] {
  presets = presets.filter((p) => Math.abs(p.frequency - frequency) > 0.01)
  emit('presets', presets)
  return presets
}

export function runScan(identify: boolean): Signal[] {
  scanned = BROADCASTS.map((b) => ({
    frequency: b.frequency,
    power: b.power,
    name: b.name,
    /* Without identify a sweep finds peaks but cannot name them:
       reading a name means tuning each one in turn. */
    rds_name: identify ? b.name : '',
    pi: identify ? b.pi : '',
  }))
  emit('signals', scanned)
  return scanned
}
