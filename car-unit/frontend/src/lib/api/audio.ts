import { request } from './client'
import type { AudioDevice, AudioState, Volume } from './types'

/* Audio.
 *
 * Volume of the default sink -- the output, the speakers. A source
 * is an input, the microphone, which nothing here touches yet.
 *
 * The daemon clamps to 100 rather than letting wpctl run past it
 * into distortion, so a caller cannot ask for more than the hardware
 * should be given.
 */

export const status = () => request<AudioState>('/audio')

export const devices = () => request<AudioDevice[]>('/audio/devices')

/**
 * Pin the default sink or source.
 *
 * wpctl writes it to WirePlumber's state, so it holds across
 * restarts. Without ever choosing one, WirePlumber picks by priority
 * at each boot and the output moves depending on what is plugged in.
 */
export const setDefault = (node_id: number) =>
  request<AudioDevice[]>('/audio/default', {
    method: 'POST',
    body: { node_id },
  })

/** One device's level, rather than whichever is default. */
export const setDeviceVolume = (node_id: number, percent: number) =>
  request<Volume>(`/audio/devices/${node_id}/volume`, {
    method: 'POST',
    body: { percent },
  })

export const setDeviceMute = (node_id: number, muted?: boolean) =>
  request<Volume>(`/audio/devices/${node_id}/mute`, {
    method: 'POST',
    body: { muted },
  })

/* One application's level.
 *
 * WirePlumber remembers these by application name, so a source set
 * quieter once stays that way across restarts. */
export const setStreamVolume = (node_id: number, percent: number) =>
  request<{ node_id: number; percent: number; muted: boolean }>(
    `/audio/streams/${node_id}/volume`,
    { method: 'POST', body: { percent } },
  )

export const setStreamMute = (node_id: number, muted: boolean) =>
  request<{ node_id: number; percent: number; muted: boolean }>(
    `/audio/streams/${node_id}/mute`,
    { method: 'POST', body: { muted } },
  )

export const microphone = () => request<Volume>('/audio/microphone')

export const setMicrophone = (percent: number) =>
  request<Volume>('/audio/microphone', {
    method: 'POST',
    body: { percent },
  })

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
