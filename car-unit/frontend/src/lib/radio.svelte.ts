import * as fm from './api/fm'
import { RequestFailed } from './api/client'
import { EMPTY_RADIO, type RadioState, type Signal, type Station } from './api/types'

/* The radio, as one piece of state the screens share.
 *
 * Every action applies what the daemon returns rather than guessing
 * locally, so the screen and the device cannot drift -- the daemon
 * clamps the band, resolves preset names and decides what "play with
 * no argument" means, and second-guessing any of that here would put
 * two answers in the system.
 */

const POLL_MS = 2000

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
 * Keep the state current while a screen is mounted.
 *
 * Polling rather than a subscription because RDS arrives gradually --
 * the station name and radiotext fill in over several seconds after
 * tuning, and there is no event to wait for.
 *
 * Returns a stop function, so an $effect can hand it straight back.
 */
export function watch(interval = POLL_MS): () => void {
  let stopped = false

  const tick = async () => {
    if (stopped) return
    /* Skipped while an action is in flight: that action is about to
       set the state itself, and a poll landing after it would show a
       reading from before the change. */
    if (!radio.busy && !radio.scanning) await refresh()
  }

  tick()
  const timer = setInterval(tick, interval)

  return () => {
    stopped = true
    clearInterval(timer)
  }
}
