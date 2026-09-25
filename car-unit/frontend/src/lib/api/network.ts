import { request } from './client'
import type {
  NetworkMode,
  NetworkState,
  WifiNetwork,
} from './types'

/* Wi-Fi and the hotspot.
 *
 * One radio, so one setting with three positions rather than two
 * switches that can contradict each other.
 */

/* Services have to stop and start, and an association has to be
   made. Well past what a request normally takes. */
const MODE_TIMEOUT = 45_000

export const status = () => request<NetworkState>('/network')

export const setMode = (mode: NetworkMode) =>
  request<NetworkState>('/network/mode', {
    method: 'POST',
    body: { mode },
    timeout: MODE_TIMEOUT,
  })

/* A sweep of the band. Slow: the card has to listen across every
   channel and the results take a moment to settle. */
const SCAN_TIMEOUT = 30_000

/* Association, DHCP, and a key exchange if there is one. */
const JOIN_TIMEOUT = 60_000

export const scan = (rescan = true) =>
  request<WifiNetwork[]>('/network/networks', {
    query: { rescan },
    timeout: SCAN_TIMEOUT,
  })

export const connect = (ssid: string, password?: string) =>
  request<NetworkState>('/network/connect', {
    method: 'POST',
    body: { ssid, password },
    timeout: JOIN_TIMEOUT,
  })

export const disconnect = () =>
  request<NetworkState>('/network/disconnect', { method: 'POST' })

export const forget = (ssid: string) =>
  request<NetworkState>(`/network/networks/${encodeURIComponent(ssid)}`, {
    method: 'DELETE',
  })
