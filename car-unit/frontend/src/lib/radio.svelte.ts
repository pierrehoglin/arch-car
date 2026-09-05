import * as fm from './api/fm'
import { RequestFailed } from './api/client'
import { connect, on, stream } from './api/stream.svelte'
import { EMPTY_RADIO, type RadioState, type Signal, type Station } from './api/types'

/* The radio, as one piece of state the screens share.
 *
 * Every action applies what the daemon returns rather than guessing
 * locally, so the screen and the device cannot drift -- the daemon
 * clamps the band, resolves preset names and decides what "play with
 * no argument" means, and second-guessing any of that here would put
 * two answers in the system.
 *
 * Updates arrive over the event stream rather than by polling. RDS
 * fills in a couple of seconds after tuning and the supervisor can
 * change the source at any moment, neither of which a two-second poll
 * reports promptly -- and most polls would find nothing changed.
 */

interface Store {
  state: RadioState
  presets: Station[]
  /** What the last scan found. Empty until one has run. */
  signals: Signal[]
  scanning: boolean
  busy: boolean
  error: string
}

export const radio = $state<Store>({
  state: EMPTY_RADIO,
  presets: [],
  signals: [],
  scanning: false,
  busy: false,
  error: '',
})

function report(cause: unknown): void {
  radio.error =
    cause instanceof RequestFailed
      ? cause.message
      : cause instanceof Error
        ? cause.message
        : String(cause)
}

/** Run an action, applying whatever state comes back. */
async function act(action: () => Promise<RadioState>): Promise<void> {
  radio.busy = true
  try {
    radio.state = await action()
    radio.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    radio.busy = false
  }
}

export const play = (station?: string | number) =>
  act(() => fm.play(station))
export const pause = () => act(fm.pause)
export const toggle = () => act(fm.toggle)
export const stop = () => act(fm.stop)
export const tune = (offset: number) => act(() => fm.tune(offset))
export const seek = (direction: 1 | -1) => act(() => fm.seek(direction))

export async function refresh(): Promise<void> {
  try {
    radio.state = await fm.status()
    radio.error = ''
  } catch (cause) {
    report(cause)
  }
}

export async function loadPresets(): Promise<void> {
  try {
    radio.presets = await fm.presets()
  } catch (cause) {
    report(cause)
  }
}

export async function savePreset(frequency: number, name = ''): Promise<void> {
  try {
    radio.presets = await fm.savePreset(frequency, name)
  } catch (cause) {
    report(cause)
  }
}

export async function reorderPresets(stations: Station[]): Promise<void> {
  /* Applied straight away rather than waiting for the response: the
     list is already under the user's finger, and having it snap back
     for a moment would read as the drag having failed. */
  const previous = radio.presets
  radio.presets = stations

  try {
    radio.presets = await fm.reorderPresets(stations)
  } catch (cause) {
    radio.presets = previous
    report(cause)
  }
}

export async function forgetPreset(frequency: number): Promise<void> {
  try {
    radio.presets = await fm.forgetPreset(frequency)
  } catch (cause) {
    report(cause)
  }
}

/**
 * Sweep the band.
 *
 * Guarded against overlapping runs: a scan holds the one RTL-SDR
 * device, so a second would fail on a busy dongle rather than queue.
 */
export async function scan(identify = true): Promise<void> {
  if (radio.scanning) return

  radio.scanning = true
  radio.error = ''
  try {
    radio.signals = await fm.scan(identify)
  } catch (cause) {
    report(cause)
  } finally {
    radio.scanning = false
  }
}

/**
 * Follow the daemon.
 *
 * Opens the stream if it is not already open and subscribes to what
 * the radio cares about. Returns an unsubscribe function, so an
 * $effect can hand it straight back.
 *
 * The stream sends current state on connecting, so a screen mounting
 * halfway through a session is populated without also fetching.
 */
export function watch(): () => void {
  connect()

  const off = [
    on('fm', (data) => {
      /* Ignored while an action is in flight: that action is about to
         set the state itself, and an event landing after it would
         show a reading from before the change. */
      if (!radio.busy) radio.state = data as RadioState
    }),
    on('presets', (data) => {
      radio.presets = data as Station[]
    }),
    on('signals', (data) => {
      radio.signals = data as Signal[]
    }),
  ]

  return () => {
    for (const stop of off) stop()
  }
}

/** Whether readings are live, for a screen that wants to say so. */
export const connection = () => stream.connection
