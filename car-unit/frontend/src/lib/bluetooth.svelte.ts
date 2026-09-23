import * as api from './api/bluetooth'
import { on } from './api/stream.svelte'
import { RequestFailed } from './api/client'
import type { BtDevice, BtState, PairingRequest } from './api/types'

/* Bluetooth, shared by the settings screen and anything else that
 * wants to know what is connected.
 *
 * The daemon publishes the whole state on the stream whenever it
 * changes, so there is nothing to poll: a phone reconnecting on
 * ignition, a device appearing during a scan, a pairing finishing.
 * Actions here only ask; the answer arrives the same way as a change
 * nobody asked for.
 */

const EMPTY: BtState = {
  adapter: {
    path: '',
    address: '',
    name: '',
    powered: false,
    discoverable: false,
    pairable: false,
    discovering: false,
    service_active: false,
  },
  devices: [],
  window: { open: false, seconds_left: 0 },
  attempt: null,
}

interface Store {
  state: BtState
  /** A pairing waiting to be confirmed, if any. */
  request: PairingRequest | null
  /** Addresses with something in flight, so a row can show it. */
  busy: string[]
  /** True while the service is being started or stopped. */
  switching: boolean
  error: string
}

export const bluetooth = $state<Store>({
  state: EMPTY,
  request: null,
  busy: [],
  switching: false,
  error: '',
})

/* Not $state: an $effect reading it would re-run when a request
   settled, and a store that starts its own requests would never
   stop. */
let settling = false

export const searching = () => bluetooth.state.window.open

/** An address with the separators taken out, for comparing. */
const bare = (text: string) => text.replace(/[^0-9a-f]/gi, '').toUpperCase()

/* Whether BlueZ has learned what a device calls itself.
 *
 * Three shapes mean it has not. The daemon substitutes "(unnamed)"
 * when neither Alias nor Name is set; the name can be blank; and
 * BlueZ's own fallback Alias is the address written with hyphens --
 * 5C-11-22-33-44-55 against an address of 5C:11:22:33:44:55 -- so the
 * two have to be compared with the separators taken out.
 *
 * A scan turns up a great many of these: beacons, tags, cars going
 * past. None is anything anyone would choose to connect to.
 */
function named(device: BtDevice): boolean {
  const name = device.name.trim()
  if (!name || name === '(unnamed)') return false

  const digits = bare(name)
  /* Only when it is the whole name: a device genuinely called
     "Erik 33:44" should not be dropped for containing hex. */
  return digits.length !== 12 || digits !== bare(device.address)
}

/**
 * The devices worth showing.
 *
 * Everything BlueZ knows of that has told us what it is. Devices
 * found by a scan stay listed once it ends -- BlueZ keeps them for a
 * while, and dropping them meant a device you had just seen vanished
 * the moment you stopped looking. With the nameless ones gone there
 * are few enough that leaving them is no clutter.
 *
 * The name rule is not applied to saved devices. One without a name
 * should not happen, but if it did, hiding it would leave something
 * paired to the car that cannot be seen or forgotten.
 */
export const devices = () =>
  bluetooth.state.devices.filter(
    (device) => device.paired || named(device),
  )

/* BlueZ's own icon names, mapped onto ours.
 *
 * BlueZ derives these from the device's class of device -- the same
 * field the car sets for itself -- so they are as good as what the
 * device reports about itself, which for a phone is reliable and for
 * a no-name dongle is often nothing at all.
 */
const ICONS: Record<string, string> = {
  'audio-card': 'speaker',
  'audio-headphones': 'headphones',
  'audio-headset': 'headset',
  camera: 'camera',
  'camera-photo': 'camera',
  'camera-video': 'camera',
  computer: 'laptop',
  'input-gaming': 'gamepad',
  'input-keyboard': 'keyboard',
  'input-mouse': 'mouse',
  'input-tablet': 'mobile',
  modem: 'router',
  'multimedia-player': 'speaker',
  'network-wireless': 'router',
  phone: 'mobile',
  printer: 'printer',
  'video-display': 'tv',
}

/**
 * Which icon to draw for a device.
 *
 * Falls back to the Bluetooth mark rather than a guess: a device that
 * does not say what it is looks like nothing in particular, and an
 * arbitrary icon would be a claim the device never made.
 */
export const iconFor = (icon: string) => ICONS[icon] ?? 'bluetooth'

/** Whatever is connected, for the line under the switch. */
export const connected = (): BtDevice | undefined =>
  bluetooth.state.devices.find((device) => device.connected)

const isBusy = (address: string) =>
  bluetooth.busy.includes(address.toUpperCase())

/**
 * Whether a row has something in flight.
 *
 * Not just our own request: pairing returns as soon as BlueZ has
 * something to ask about, and carries on until the code is confirmed.
 * Going by the request alone, the button would settle back to Pair a
 * tenth of a second in, which reads as having failed -- and then the
 * dialog appears, contradicting it.
 */
export function busyWith(address: string): boolean {
  const key = address.toUpperCase()
  if (isBusy(key)) return true

  const attempt = bluetooth.state.attempt
  if (attempt?.address === key && attempt.state === 'pairing') return true

  return bluetooth.request?.address.toUpperCase() === key
}


function report(cause: unknown): void {
  bluetooth.error =
    cause instanceof RequestFailed || cause instanceof Error
      ? cause.message
      : String(cause)
}

/** Run an action for one device, marking the row while it runs. */
async function act(address: string, call: () => Promise<unknown>) {
  const key = address.toUpperCase()
  if (isBusy(key)) return

  bluetooth.busy = [...bluetooth.busy, key]
  settling = true
  try {
    await call()
    bluetooth.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    bluetooth.busy = bluetooth.busy.filter((held) => held !== key)
    settling = false
    await refresh()
  }
}

export async function refresh(): Promise<void> {
  try {
    bluetooth.state = await api.status()
  } catch (cause) {
    report(cause)
  }
}

/**
 * Turn the service on or off.
 *
 * Slower than it looks: bluetoothd has to come up, the adapter has to
 * appear, and oFono re-registers behind it. The switch shows as busy
 * throughout rather than flicking back when the first reading still
 * says off.
 */
export async function setService(active: boolean): Promise<void> {
  if (bluetooth.switching) return

  bluetooth.switching = true
  settling = true
  try {
    await api.setService(active)
    bluetooth.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    bluetooth.switching = false
    settling = false
    await refresh()
  }
}

/** Open the pairing window, or close it if it is already open. */
export async function toggleSearch(seconds = 120): Promise<void> {
  settling = true
  try {
    if (searching()) await api.closeWindow()
    else await api.openWindow(seconds)
    bluetooth.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    settling = false
    await refresh()
  }
}

export const connect = (address: string) =>
  act(address, () => api.connect(address))

export const disconnect = (address: string) =>
  act(address, () => api.disconnect(address))

export const forget = (address: string) =>
  act(address, () => api.forget(address))

/** Pair, for a device that has been found but never bonded. */
export const pair = (address: string) =>
  act(address, () => api.pair(address))

export async function answer(accept: boolean): Promise<void> {
  try {
    await api.answer(accept)
  } catch (cause) {
    report(cause)
  }
}

/**
 * Follow the daemon.
 *
 * Subscribes only -- the connection belongs to the root layout.
 */
export function watch(): () => void {
  const off = [
    on('bluetooth', (data) => {
      /* Ignored while an action is in flight: it is about to set the
         state itself, and an event from before the change would show
         the row as it was. */
      if (!settling) bluetooth.state = data as BtState
    }),
    on('pairing', (data) => {
      bluetooth.request = (data as PairingRequest | null) ?? null
    }),
  ]

  return () => {
    for (const stop of off) stop()
  }
}
