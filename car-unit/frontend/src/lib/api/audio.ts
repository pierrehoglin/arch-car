import { request } from './client'
import type { Volume } from './types'

/* Audio.
 *
 * Volume of the default sink -- the output, the speakers. A source
 * is an input, the microphone, which nothing here touches yet.
 *
 * The daemon clamps to 100 rather than letting wpctl run past it
 * into distortion, so a caller cannot ask for more than the hardware
 * should be given.
 */

export const status = () => request<Volume>('/audio')

export const setVolume = (percent: number) =>
  request<Volume>('/audio/volume', { method: 'POST', body: { percent } })

/**
 * Step the volume.
 *
 * Preferred over reading and setting: the daemon does both in one
 * call, so nothing can change in between -- which matters once the
 * steering wheel buttons are wired and two things are adjusting it.
 */
export const adjust = (delta: number) =>
  request<Volume>('/audio/adjust', { method: 'POST', body: { delta } })

/** `muted` omitted toggles, which is what a single button wants. */
export const mute = (muted?: boolean) =>
  request<Volume>('/audio/mute', { method: 'POST', body: { muted } })
