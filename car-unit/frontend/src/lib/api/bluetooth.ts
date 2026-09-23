import { request } from './client'
import type { BtState, BtWindow, PairingRequest } from './types'

/* Bluetooth.
 *
 * On and off is bluetooth.service, not the radio: stopping it tears
 * down the daemon, and oFono is PartOf it, so calls go too -- which is
 * what off should mean in a car.
 *
 * Pairing mode is one window with three things in it: scanning, being
 * discoverable, and accepting pairings. Outside it the car is
 * invisible to new devices, but phones already paired still reconnect.
 */

/** Starting the service takes a moment, and so does stopping it. */
const SERVICE_TIMEOUT = 20_000

export const status = () => request<BtState>('/bluetooth')

export const setService = (active: boolean) =>
  request<unknown>('/bluetooth/service', {
    method: 'POST',
    body: { active },
    timeout: SERVICE_TIMEOUT,
  })

export const openWindow = (seconds = 120) =>
  request<BtWindow>('/bluetooth/pairing-mode', {
    method: 'POST',
    body: { seconds },
  })

export const closeWindow = () =>
  request<BtWindow>('/bluetooth/pairing-mode', { method: 'DELETE' })

export const pending = () =>
  request<PairingRequest | null>('/bluetooth/pairing')

export const answer = (accept: boolean) =>
  request<{ answered: boolean }>('/bluetooth/pairing', {
    method: 'POST',
    body: { accept },
  })

/** Starts pairing and returns; progress arrives on the stream. */
export const pair = (address: string) =>
  request<unknown>(`/bluetooth/devices/${address}/pair`, { method: 'POST' })

export const connect = (address: string) =>
  request<unknown>(`/bluetooth/devices/${address}/connect`, {
    method: 'POST',
    /* Connecting brings up every profile the phone offers, which on a
       cold link is slower than it sounds. */
    timeout: 30_000,
  })

export const disconnect = (address: string) =>
  request<unknown>(`/bluetooth/devices/${address}/disconnect`, {
    method: 'POST',
  })

export const forget = (address: string) =>
  request<unknown>(`/bluetooth/devices/${address}`, { method: 'DELETE' })
