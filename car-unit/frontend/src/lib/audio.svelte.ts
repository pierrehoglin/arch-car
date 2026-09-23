import * as api from './api/audio'
import { on } from './api/stream.svelte'
import { RequestFailed } from './api/client'
import type { AudioDevice, AudioState, Volume } from './api/types'

/* The volume, shared by everything that shows or changes it.
 *
 * Every change is applied locally first and sent as it was made: a
 * press of the button is one step, a move of the slider is one
 * level. Nothing is combined or rewritten on the way out.
 *
 * What keeps it steady is that a response is only believed if
 * nothing has been asked for since it was sent. Press twice quickly
 * and the first answer describes the volume before the second press
 * -- applying it would drag the reading backwards, which is what
 * makes a slider jump about.
 *
 * The slider is the one exception to sending everything: it fires an
 * event per pixel, so only the last position of a drag is sent.
 */

/** Long enough to collapse a drag, short enough to be inaudible. */
const WRITE_DELAY = 120

/* Events are ignored for a moment after a write settles. The daemon
   echoes our own change on the stream, and that echo is in flight
   when the response arrives. */
const QUIET_AFTER_WRITE = 250

interface Store {
  percent: number
  muted: boolean
  /** The microphone, which HFP calls use. Its own level, not the
   *  output's. */
  mic: number
  micMuted: boolean
  /** Every sink and source, with the default of each marked. */
  devices: AudioDevice[]
  /** Whether the daemon has ever answered, so a screen can tell a
   *  real reading from the default. */
  known: boolean
  error: string
}

export const audio = $state<Store>({
  percent: 50,
  muted: false,
  mic: 50,
  micMuted: false,
  devices: [],
  known: false,
  error: '',
})

/** The sinks, output first in the order the daemon gave them. */
export const sinks = () =>
  audio.devices.filter((device) => device.kind === 'sink')

export const sources = () =>
  audio.devices.filter((device) => device.kind === 'source')


/* None of this is $state: an $effect reading any of it would re-run
   when a write settled, and a store that starts its own writes would
   never stop. */
let ticket = 0
let inflight = 0
let quietUntil = 0

/* The slider's last position, waiting out the debounce. Held here
   rather than captured by the timer, because a button pressed during
   that window has to know it is there. */
let timer: ReturnType<typeof setTimeout> | undefined
let level: number | null = null

/* Set when a change un-mutes, cleared when the unmute is sent. It
   has to outlive a single call: during a drag only the first pixel
   sees audio.muted as true, and the write that eventually goes is
   the last one. */
let needsUnmute = false

const clamp = (percent: number) =>
  Math.max(0, Math.min(100, Math.round(percent)))

function apply(volume: Volume): void {
  audio.percent = volume.percent
  audio.muted = volume.muted
  audio.known = true
  audio.error = ''
}

/* The whole reading, from the stream or a status call. Devices are
   taken even while a write is settling: a write changes the volume,
   never the device list, so there is nothing for them to contradict. */
function applyState(reading: AudioState): void {
  if (!deviceTimers.size) audio.devices = reading.devices
  audio.mic = reading.microphone.percent
  audio.micMuted = reading.microphone.muted
  apply(reading.volume)
}

function report(cause: unknown): void {
  audio.error =
    cause instanceof RequestFailed || cause instanceof Error
      ? cause.message
      : String(cause)
}

/** Read everything once, for a screen that opens mid-session. */
export async function refresh(): Promise<void> {
  try {
    applyState(await api.status())
  } catch (cause) {
    report(cause)
  }
}

/**
 * Choose the default sink or source.
 *
 * The response is the new device list, so the picker settles without
 * waiting for the stream to come round.
 */
export async function setDefault(node_id: number): Promise<void> {
  try {
    audio.devices = await api.setDefault(node_id)
    audio.error = ''
  } catch (cause) {
    report(cause)
  }
}

/* A write per device, each with its own debounce: two sliders can be
   moved in a session and the second must not cancel the first. Keyed
   by node id, and dropped when the write goes. */
const deviceTimers = new Map<number, ReturnType<typeof setTimeout>>()

function patch(node_id: number, change: Partial<AudioDevice>): void {
  audio.devices = audio.devices.map((device) =>
    device.node_id === node_id ? { ...device, ...change } : device,
  )
}

/**
 * Set one device's level. Applies at once; the write follows.
 *
 * Moving the default sink here is the same thing the header slider
 * does -- they are one level, and each will show the other move.
 */
export function setDeviceVolume(node_id: number, percent: number): void {
  const level = clamp(percent)
  patch(node_id, { percent: level, muted: false })

  clearTimeout(deviceTimers.get(node_id))
  deviceTimers.set(
    node_id,
    setTimeout(async () => {
      deviceTimers.delete(node_id)
      try {
        const volume = await api.setDeviceVolume(node_id, level)
        patch(node_id, { percent: volume.percent, muted: volume.muted })
      } catch (cause) {
        report(cause)
      }
    }, WRITE_DELAY),
  )
}

export async function setDeviceMute(
  node_id: number,
  muted: boolean,
): Promise<void> {
  patch(node_id, { muted })
  try {
    const volume = await api.setDeviceMute(node_id, muted)
    patch(node_id, { percent: volume.percent, muted: volume.muted })
  } catch (cause) {
    report(cause)
  }
}

/**
 * Note that something has been asked for.
 *
 * Counted here, when the intent is formed, rather than when it is
 * sent: a press arriving while an earlier request is in flight is
 * exactly what makes that request's answer out of date, and the
 * moment it was dispatched says nothing about that.
 */
function intend(): void {
  ticket += 1
  clearTimeout(timer)
  timer = undefined
}

/**
 * Reaching for the volume means you want to hear something.
 *
 * Applied here and returned, because it also has to be sent: wpctl's
 * set-volume leaves a muted sink muted, so a level on its own would
 * be silent with the slider showing otherwise.
 */
function unmuting(): void {
  if (!audio.muted) return
  audio.muted = false
  needsUnmute = true
}

async function send(call: () => Promise<Volume>): Promise<void> {
  const mine = ticket
  const unmute = needsUnmute
  needsUnmute = false
  inflight += 1

  try {
    // Before the level, so it applies to a sink that is audible.
    if (unmute) await api.mute(false)

    const volume = await call()
    if (mine === ticket) apply(volume)
  } catch (cause) {
    // Still muted, so the next write should try again.
    if (unmute) needsUnmute = true

    audio.error =
      cause instanceof RequestFailed || cause instanceof Error
        ? cause.message
        : String(cause)
  } finally {
    inflight -= 1
    quietUntil = Date.now() + QUIET_AFTER_WRITE
  }
}

/**
 * Step the volume.
 *
 * Sent as the step it was, not as a level: the daemon reads and sets
 * in one call, so nothing can change in between -- which will matter
 * once the steering wheel buttons are wired.
 */
export function adjust(delta: number): void {
  audio.percent = clamp(audio.percent + delta)
  unmuting()

  /* A drag still waiting to be sent means the daemon is behind by
     more than this step, and a step against its stale level would
     land in the wrong place. The reading already includes both, so
     send that instead. */
  const pending = level !== null
  const wanted = audio.percent

  intend()
  level = null

  send(pending ? () => api.setVolume(wanted) : () => api.adjust(delta))
}

/** Set the volume. Applies at once; the last position is sent. */
export function setVolume(percent: number): void {
  audio.percent = clamp(percent)
  unmuting()

  intend()
  level = audio.percent

  timer = setTimeout(() => {
    const wanted = level
    timer = undefined
    level = null
    if (wanted !== null) send(() => api.setVolume(wanted))
  }, WRITE_DELAY)
}

export function setMuted(muted: boolean): void {
  audio.muted = muted

  intend()
  level = null
  needsUnmute = false

  send(() => api.mute(muted))
}

/**
 * Follow the daemon.
 *
 * Subscribes only -- the connection belongs to the root layout. The
 * stream carries changes from anywhere: the CLI, another program,
 * and the steering wheel once CAN is wired. A UI that only saw its
 * own changes would drift the first time something else moved it.
 */
export function watch(): () => void {
  return on('audio', (data) => {
    const reading = data as AudioState

    /* Devices carry their own levels now, so an event arriving while
       a slider is being dragged would describe them as they were.
       Held back for the same window as the volume. */
    if (inflight > 0 || deviceTimers.size || Date.now() < quietUntil) {
      return
    }

    audio.devices = reading.devices
    audio.mic = reading.microphone.percent
    audio.micMuted = reading.microphone.muted
    apply(reading.volume)
  })
}
