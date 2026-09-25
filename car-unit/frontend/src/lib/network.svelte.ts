import * as api from './api/network'
import { on } from './api/stream.svelte'
import { RequestFailed } from './api/client'
import type {
  NetworkMode,
  NetworkState,
  WifiNetwork,
} from './api/types'

/* The radio: Wi-Fi, or the hotspot, or neither.
 *
 * One setting with two positions rather than two switches. They share
 * an interface, so a car cannot be on a network and serving one at
 * the same time -- two switches would let the screen ask for
 * something impossible and then show whichever answer arrived last.
 *
 * There is no off. The car is either on a network or serving one.
 */

const EMPTY: NetworkState = {
  wifi: {
    enabled: false,
    connected: false,
    ssid: '',
    signal: null,
    ip_address: '',
    device: '',
  },
  hotspot: {
    active: false,
    ssid: '',
    channel: null,
    band: '',
    interface: '',
    address: '',
    uplink: '',
    clients: [],
  },
}

interface Store {
  state: NetworkState
  /** What the last sweep found. */
  networks: WifiNetwork[]
  /** True while the card is sweeping the band. */
  scanning: boolean
  /** The SSID with something in flight, so its row can show it. */
  busy: string
  /** True while a mode change is in flight. It is slow: services
   *  stop and start, and an association has to be made. */
  changing: boolean
  error: string
}

export const network = $state<Store>({
  state: EMPTY,
  networks: [],
  scanning: false,
  busy: '',
  changing: false,
  error: '',
})

/* Not $state: an $effect reading it would re-run when a change
   settled, and this store starts its own changes. */
let settling = false

/**
 * Which position the radio is in.
 *
 * Anything that is not the hotspot is Wi-Fi, including the radio
 * being off entirely -- which happens at boot before anything has
 * come up. Reporting that as a third state would mean a control with
 * a position nobody can choose; reporting it as Wi-Fi means picking
 * Wi-Fi puts it right.
 */
export function mode(): NetworkMode {
  return network.state.hotspot.active ? 'hotspot' : 'wifi'
}

/** Whether the car is actually on a network, rather than merely on. */
export const online = () =>
  network.state.wifi.connected || network.state.hotspot.active

function report(cause: unknown): void {
  network.error =
    cause instanceof RequestFailed || cause instanceof Error
      ? cause.message
      : String(cause)
}

export async function refresh(): Promise<void> {
  try {
    network.state = await api.status()
  } catch (cause) {
    report(cause)
  }
}

/**
 * Move the radio to a position.
 *
 * Nothing is applied optimistically. Turning a hotspot on takes
 * seconds and can fail -- no uplink, hostapd refusing the channel --
 * and a switch that flipped first would then have to flip back.
 */
export async function setMode(next: NetworkMode): Promise<void> {
  if (network.changing || next === mode()) return

  network.changing = true
  settling = true
  try {
    network.state = await api.setMode(next)
    network.error = ''
  } catch (cause) {
    report(cause)
    await refresh()
  } finally {
    network.changing = false
    settling = false
  }
}

/* Networks worth listing.
 *
 * Nameless ones dropped: a hidden network broadcasts an empty SSID,
 * and a row with no name is one nobody can choose. Strongest first,
 * with whatever is joined at the top -- that is the one being looked
 * for when the list is opened.
 */
export const networks = () =>
  network.networks
    .filter((found) => found.ssid.trim())
    .sort(
      (a, b) =>
        Number(b.in_use) - Number(a.in_use) ||
        Number(b.saved) - Number(a.saved) ||
        b.signal - a.signal,
    )

/** Whether a network needs a password the first time. */
export const secured = (found: WifiNetwork) =>
  !!found.security && found.security !== '--'

/**
 * Sweep the band.
 *
 * `rescan` false returns the last sweep, which is what a screen
 * re-opening wants -- asking the card to listen again takes seconds
 * and finds the same thing.
 */
export async function scan(rescan = true): Promise<void> {
  if (network.scanning) return

  network.scanning = true
  try {
    network.networks = await api.scan(rescan)
    network.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    network.scanning = false
  }
}

/** Run something for one network, marking its row while it runs. */
async function act(ssid: string, call: () => Promise<NetworkState>) {
  if (network.busy) return

  network.busy = ssid
  settling = true
  try {
    network.state = await call()
    network.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    network.busy = ''
    settling = false
    /* Without a rescan: joining changes which network is in use, and
       the list has to show that -- but the band has not changed. */
    await scan(false)
  }
}

export const join = (ssid: string, password?: string) =>
  act(ssid, () => api.connect(ssid, password))

export const disconnect = () =>
  act(network.state.wifi.ssid, () => api.disconnect())

export const forget = (ssid: string) =>
  act(ssid, () => api.forget(ssid))

/**
 * Follow the daemon.
 *
 * Subscribes only -- the connection belongs to the root layout.
 */
export function watch(): () => void {
  return on('network', (data) => {
    if (settling) return
    network.state = data as NetworkState
  })
}
