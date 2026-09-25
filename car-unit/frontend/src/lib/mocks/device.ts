import type {
  AudioDevice,
  RadioState,
  Signal,
  Station,
  Volume,
} from '../api/types'
import {
  BROADCASTS,
  BT_ADAPTER,
  BT_DEVICES,
  INITIAL,
  PRESETS,
  stateFor,
  type BtFixture,
} from './fixtures'

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

let volume: Volume = { percent: 47, muted: false, target: 'sink' }
let mic: Volume = { percent: 62, muted: false, target: 'source' }

/* Two sinks and two sources, as the unit really has: the DAC it
   drives the speakers with, a headset that turns up over USB, and the
   microphones that go with them. Node ids are PipeWire's, which
   change when a device is re-plugged -- so nothing should store
   them. */
let audioDevices: AudioDevice[] = [
  { node_id: 51, name: 'CarPiHat DAC Analog Stereo', is_default: true,
    kind: 'sink', percent: 47, muted: false },
  { node_id: 87, name: 'CORSAIR VIRTUOSO XT Analog Stereo',
    is_default: false, kind: 'sink', percent: 100, muted: true },
  { node_id: 65, name: 'CORSAIR VIRTUOSO XT Mono', is_default: true,
    kind: 'source', percent: 62, muted: false },
  { node_id: 93, name: 'Pierre Pixel (Handsfree)', is_default: false,
    kind: 'source', percent: 85, muted: false },
]

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
     new one goes on the end. Sorting by frequency here would throw
     away a reorder on the next rename -- the daemon does the same. */
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
  /* Matched by frequency, as the daemon does: the names in the
     request are not taken on trust, so a rename that raced with a
     drag cannot overwrite the stored one. Anything left out keeps
     its place at the end. */
  const held = new Map(presets.map((p) => [p.frequency.toFixed(1), p]))
  const ordered: Station[] = []

  for (const wanted of next) {
    const key = wanted.frequency.toFixed(1)
    const station = held.get(key)
    if (station) {
      ordered.push(station)
      held.delete(key)
    }
  }

  presets = [...ordered, ...held.values()]
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


/* Audio.
 *
 * Clamped to 100 as the daemon does, rather than letting a caller
 * ask for more than the hardware should be given.
 */

/* The whole reading, which is what both /api/audio and the stream
   send -- one shape, so a screen can start from either. */
/* What is playing. Named as the graph names them -- carlib labels
   its own node, and spotifyd arrives through the ALSA plugin, which
   labels the stream after the plugin. The frontend maps those to
   something readable. */
let audioStreams = [
  { id: 73, name: 'spotifyd', application: 'PipeWire ALSA [spotifyd]',
    description: 'PipeWire ALSA [spotifyd]',
    media_class: 'Stream/Output/Audio', state: 'running',
    binary: 'spotifyd', percent: 62, muted: false },
  { id: 91, name: 'carlib-fm', application: 'carlib-fm',
    description: 'carlib-fm',
    media_class: 'Stream/Output/Audio', state: 'idle',
    binary: 'rtl_fm', percent: 38, muted: false },
  {
    /* A phone over A2DP: WirePlumber makes it a playback stream, not
       a source, and it sets no application name at all. */
    id: 105, name: 'bluez_input.20_F0_94_03_AB_DF.2', application: '',
    description: 'Pierre Pixel',
    media_class: 'Stream/Output/Audio', state: 'running',
    binary: '', percent: 74, muted: false },
]

export const audioState = () => ({
  volume: { ...volume },
  microphone: { ...mic },
  devices: audioDevices.map((device) => ({ ...device })),
  streams: audioStreams.map((stream) => ({ ...stream })),
})

export const allStreams = () => audioStreams

export function setStreamVolume(id: number, percent: number) {
  const level = Math.max(0, Math.min(100, Math.round(percent)))
  audioStreams = audioStreams.map((stream) =>
    stream.id === id ? { ...stream, percent: level, muted: false } : stream,
  )
  audioChanged()
  const changed = audioStreams.find((stream) => stream.id === id)
  return { node_id: id, percent: changed?.percent ?? 0,
           muted: changed?.muted ?? false }
}

export function setStreamMute(id: number, muted: boolean) {
  audioStreams = audioStreams.map((stream) =>
    stream.id === id ? { ...stream, muted } : stream,
  )
  audioChanged()
  const changed = audioStreams.find((stream) => stream.id === id)
  return { node_id: id, percent: changed?.percent ?? 0,
           muted: changed?.muted ?? false }
}

export const currentVolume = () => volume

function audioChanged(): void {
  emit('audio', audioState())
}

function setVolume(next: Volume): Volume {
  volume = next

  // The other direction of the same rule: the headline volume is the
  // default sink's level.
  audioDevices = audioDevices.map((device) =>
    device.is_default && device.kind === 'sink'
      ? { ...device, percent: next.percent, muted: next.muted }
      : device,
  )

  audioChanged()
  return volume
}

export function setMicrophone(percent: number): Volume {
  const level = Math.max(0, Math.min(100, Math.round(percent)))
  mic = { ...mic, percent: level }

  audioDevices = audioDevices.map((device) =>
    device.is_default && device.kind === 'source'
      ? { ...device, percent: level }
      : device,
  )

  audioChanged()
  return mic
}

export const currentMicrophone = () => mic

export function setDefaultDevice(nodeId: number): AudioDevice[] {
  const chosen = audioDevices.find((device) => device.node_id === nodeId)
  if (!chosen) return audioDevices

  // Per kind: choosing an output does not unset the input.
  audioDevices = audioDevices.map((device) =>
    device.kind === chosen.kind
      ? { ...device, is_default: device.node_id === nodeId }
      : device,
  )

  audioChanged()
  return audioDevices
}

export const allAudioDevices = () => audioDevices

function patchDevice(nodeId: number, change: Partial<AudioDevice>) {
  audioDevices = audioDevices.map((device) =>
    device.node_id === nodeId ? { ...device, ...change } : device,
  )

  /* The default sink is what the headline volume reads, so moving it
     here moves that too -- they are one level, not two that happen to
     agree. */
  const changed = audioDevices.find((device) => device.node_id === nodeId)
  if (changed?.is_default && changed.kind === 'sink') {
    volume = { ...volume, percent: changed.percent, muted: changed.muted }
  }
  if (changed?.is_default && changed.kind === 'source') {
    mic = { ...mic, percent: changed.percent, muted: changed.muted }
  }

  audioChanged()
  return changed
}

export function setDeviceVolume(nodeId: number, percent: number) {
  return patchDevice(nodeId, {
    percent: Math.max(0, Math.min(100, Math.round(percent))),
    muted: false,
  })
}

export function setDeviceMute(nodeId: number, muted: boolean) {
  return patchDevice(nodeId, { muted })
}

export const setPercent = (percent: number) =>
  setVolume({ ...volume, percent: Math.max(0, Math.min(100, Math.round(percent))) })

export const adjustVolume = (delta: number) =>
  setPercent(volume.percent + delta)

export const setMuted = (muted: boolean) => setVolume({ ...volume, muted })

export const toggleMuted = () => setVolume({ ...volume, muted: !volume.muted })


/* Bluetooth.
 *
 * The same shape the daemon publishes: adapter, devices, the pairing
 * window, and how the last pairing went.
 */

let adapter = { ...BT_ADAPTER }
let bt: BtFixture[] = BT_DEVICES.map((device) => ({ ...device }))
let window_ = { open: false, seconds_left: 0 }
let closer: ReturnType<typeof setTimeout> | undefined
let ticking: ReturnType<typeof setInterval> | undefined

function btState() {
  return {
    adapter: { ...adapter },
    /* A device BlueZ has never discovered does not exist as far as
       it is concerned. Once a scan has found one it stays on the bus,
       so `nearby` here means "not found yet" rather than "only while
       looking". */
    devices: bt
      .filter((device) => !device.nearby)
      .map(({ nearby, ...device }) => device)
      .sort((a, b) =>
        Number(b.connected) - Number(a.connected) ||
        Number(b.paired) - Number(a.paired) ||
        a.name.localeCompare(b.name),
      ),
    window: { ...window_ },
    attempt: btAttempt,
  }
}

let btAttempt: { address: string; state: string; error: string } | null = null

function btChanged(): void {
  emit('bluetooth', btState())
}

export const bluetoothState = btState

export function setBluetoothService(active: boolean) {
  adapter = { ...adapter, service_active: active, powered: active }
  if (!active) stopPairingWindow()
  btChanged()
  return adapter
}

export function startPairingWindow(seconds: number) {
  const span = Math.max(10, Math.min(600, Math.round(seconds)))

  /* Found by this scan, and known from now on. Staggered, because
     devices arrive over the first seconds of a scan rather than all
     at once -- and a list that fills in is the thing the screen has
     to cope with. */
  bt.filter((device) => device.nearby).forEach((device, index) => {
    setTimeout(() => {
      device.nearby = false
      btChanged()
    }, 800 + index * 900)
  })
  window_ = { open: true, seconds_left: span }
  adapter = { ...adapter, discoverable: true, pairable: true,
              discovering: true }

  clearTimeout(closer)
  clearInterval(ticking)

  /* Counted down rather than left at the figure it started with, so
     the screen can show it running out. */
  ticking = setInterval(() => {
    window_ = { ...window_, seconds_left: Math.max(0, window_.seconds_left - 1) }
    btChanged()
  }, 1000)

  closer = setTimeout(() => stopPairingWindow(), span * 1000)

  btChanged()
  return { ...window_ }
}

export function stopPairingWindow() {
  clearTimeout(closer)
  clearInterval(ticking)
  closer = undefined
  ticking = undefined
  window_ = { open: false, seconds_left: 0 }
  adapter = { ...adapter, discoverable: false, pairable: false,
              discovering: false }
  btChanged()
  return { ...window_ }
}

function btFind(address: string): BtFixture | undefined {
  return bt.find((device) => device.address === address.toUpperCase())
}

export function btConnect(address: string) {
  const device = btFind(address)
  if (!device) return null
  // One at a time, as the car does: connecting a second phone drops
  // the first.
  bt = bt.map((each) => ({ ...each, connected: each === device }))
  btChanged()
  return btFind(address)
}

export function btDisconnect(address: string) {
  const device = btFind(address)
  if (device) device.connected = false
  btChanged()
  return device
}

/* A pairing waiting to be confirmed.
 *
 * The real agent holds BlueZ's call open while this sits here, which
 * is why the dialog has a countdown: BlueZ gives up at about thirty
 * seconds whatever the screen is doing.
 */
let btRequest: {
  device: string
  address: string
  name: string
  passkey: string | null
  kind: string
} | null = null

let btExpiry: ReturnType<typeof setTimeout> | undefined

export const btPending = () => btRequest

function askToPair(device: BtFixture): void {
  clearTimeout(btExpiry)

  btRequest = {
    device: device.path,
    address: device.address,
    name: device.name,
    // Six digits, zero-padded, as BlueZ sends them.
    passkey: String(Math.floor(Math.random() * 1_000_000)).padStart(6, '0'),
    kind: 'confirm',
  }

  btAttempt = { address: device.address, state: 'pairing', error: '' }
  emit('pairing', btRequest)
  btChanged()

  btExpiry = setTimeout(() => btAnswer(false), 28_000)
}

export function btPair(address: string) {
  const device = btFind(address)
  if (!device) return null
  askToPair(device)
  return { address: device.address, state: 'pairing', error: '' }
}

export function btAnswer(accept: boolean) {
  if (!btRequest) return { answered: false }

  clearTimeout(btExpiry)
  const device = btFind(btRequest.address)

  if (accept && device) {
    device.paired = true
    device.trusted = true
    btAttempt = { address: device.address, state: 'paired', error: '' }
  } else {
    btAttempt = {
      address: btRequest.address,
      state: 'failed',
      error: accept ? 'device went away' : 'rejected',
    }
  }

  btRequest = null
  emit('pairing', null)
  btChanged()
  return { answered: true }
}

export function btForget(address: string) {
  bt = bt.filter((device) => device.address !== address.toUpperCase())
  btChanged()
}


/* What each source is playing.
 *
 * Position advances with the clock so the progress bar has something
 * to do, and the track changes on its own after a while -- the two
 * things the screen has to cope with that a static fixture never
 * shows.
 */

const TRACKS = [
  { title: 'Burn (feat. Séb Mont)', artist: 'LUM!X, Séb Mont',
    album: 'Burn', duration: 144969,
    art: 'https://i.scdn.co/image/ab67616d0000b2739d60ccaa57b55b5543f6e700' },
  { title: 'Redbone', artist: 'Childish Gambino',
    album: 'Awaken, My Love!', duration: 326933, art: '' },
  { title: 'Alright', artist: 'Kendrick Lamar',
    album: 'To Pimp a Butterfly', duration: 219333, art: '' },
]

interface Playing {
  source: string
  device: string
  status: string
  index: number
  position: number
  since: number
  present: boolean
}

const playing: Record<string, Playing> = {
  bluetooth: {
    source: 'bluetooth', device: 'Pierre Pixel', status: 'playing',
    index: 0, position: 34496, since: Date.now(), present: true,
  },
  spotify: {
    // 'spotifyd' on the unit, 'spotify' on a desktop -- the
    // daemon reports whichever it found.
    source: 'spotify', device: 'spotifyd', status: 'paused',
    index: 1, position: 61000, since: Date.now(), present: true,
  },
}

/** Where a source has reached, with the clock taken into account. */
function at(state: Playing): number {
  if (state.status !== 'playing') return state.position
  return state.position + (Date.now() - state.since)
}

function nowPlaying(source: string) {
  const state = playing[source]
  if (!state) {
    return {
      source, device: '', status: '', title: '', artist: '', album: '',
      duration: null, position: null, art: '', track_id: '',
      present: false,
    }
  }

  const track = TRACKS[state.index % TRACKS.length]
  let position = at(state)

  // Round to the next track when this one runs out, as a real player
  // would.
  if (position >= track.duration) {
    state.index = (state.index + 1) % TRACKS.length
    state.position = 0
    state.since = Date.now()
    position = 0
    emit('media', nowPlaying(source))
  }

  const current = TRACKS[state.index % TRACKS.length]
  return {
    source,
    device: state.device,
    status: state.status,
    title: current.title,
    artist: current.artist,
    album: current.album,
    duration: current.duration,
    position: Math.round(position),
    // Only Spotify publishes art; AVRCP never does.
    art: source === 'spotify' ? current.art : '',
    track_id: `${source}/${state.index}`,
    // Only MPRIS can be seeked; AVRCP has no absolute position.
    seekable: source !== 'bluetooth',
    present: state.present,
  }
}

export const mediaNow = nowPlaying

export function mediaCommand(source: string, action: string) {
  const state = playing[source]
  if (!state) return nowPlaying(source)

  const here = at(state)

  if (action === 'play' || (action === 'toggle' && state.status !== 'playing')) {
    state.position = here
    state.since = Date.now()
    state.status = 'playing'

    /* One source at a time, as the daemon enforces. Without this the
       mock is the one place where two can play at once, which is
       exactly the case the screens are being built to handle. */
    for (const [name, other] of Object.entries(playing)) {
      if (name === source || other.status !== 'playing') continue
      other.position = at(other)
      other.since = Date.now()
      other.status = 'paused'
      emit('media', nowPlaying(name))
    }
  } else if (action === 'pause' || action === 'stop') {
    state.position = action === 'stop' ? 0 : here
    state.since = Date.now()
    state.status = action === 'stop' ? 'stopped' : 'paused'
  } else if (action === 'next' || action === 'prev') {
    const step = action === 'next' ? 1 : -1
    state.index = (state.index + step + TRACKS.length) % TRACKS.length
    state.position = 0
    state.since = Date.now()
  } else if (action === 'forward' || action === 'rewind') {
    const step = action === 'forward' ? 10_000 : -10_000
    state.position = Math.max(0, here + step)
    state.since = Date.now()
  }

  const reading = nowPlaying(source)
  emit('media', reading)
  return reading
}


export function mediaSeek(source: string, ms: number) {
  const state = playing[source]
  if (!state || source === 'bluetooth') return nowPlaying(source)

  const track = TRACKS[state.index % TRACKS.length]
  state.position = Math.max(0, Math.min(ms, track.duration))
  state.since = Date.now()

  const reading = nowPlaying(source)
  emit('media', reading)
  return reading
}


/* The radio.
 *
 * One interface, two positions: on a network, or serving one. The
 * mock enforces that too -- it is the one place two could be true at
 * once, which is exactly the state the screen exists to prevent.
 */

let net = {
  wifi: {
    enabled: true, connected: true, ssid: 'Garaget',
    signal: 72, ip_address: '192.168.1.44', device: 'wlan0',
  },
  hotspot: {
    active: false, ssid: 'car-unit', channel: null as number | null,
    band: '', interface: 'wlan0', address: '', uplink: '',
    clients: [] as unknown[],
  },
}

export const networkState = () => ({
  wifi: { ...net.wifi },
  hotspot: { ...net.hotspot, clients: [...net.hotspot.clients] },
  /* Saved profiles, whether or not they are in range. One of them --
     Sommarstugan -- is deliberately not in the air, so the list has
     something to show that a scan never finds. */
  saved: savedNames(),
})

function savedNames(): string[] {
  const names = air.filter((a) => a.saved).map((a) => a.ssid)
  for (const extra of AWAY) {
    if (!names.includes(extra)) names.push(extra)
  }
  return names
}

/* Saved but nowhere near: the summer house, seen once in July. */
const AWAY = ['Sommarstugan']

export function setNetworkMode(mode: string) {
  if (mode === 'hotspot') {
    net = {
      wifi: { ...net.wifi, enabled: false, connected: false, ssid: '',
              signal: null, ip_address: '' },
      hotspot: { ...net.hotspot, active: true, channel: 6, band: '2.4 GHz',
                 address: '192.168.50.1', uplink: 'wwan0' },
    }
  } else {
    net = {
      wifi: { ...net.wifi, enabled: true, connected: true, ssid: 'Garaget',
              signal: 72, ip_address: '192.168.1.44' },
      hotspot: { ...net.hotspot, active: false, channel: null, band: '',
                 address: '', uplink: '', clients: [] },
    }
  }

  emit('network', networkState())
  return networkState()
}


/* Networks in range.
 *
 * A mix on purpose: one joined, one saved but out of use, open ones,
 * a weak one, and a nameless hidden network the list has to drop.
 */
const AIR = [
  { ssid: 'Garaget', signal: 74, security: 'WPA2', channel: '6',
    rate: '270 Mbit/s', in_use: true, saved: true },
  { ssid: 'Huset', signal: 61, security: 'WPA2', channel: '11',
    rate: '270 Mbit/s', in_use: false, saved: true },
  { ssid: 'Grannen_5G', signal: 47, security: 'WPA3', channel: '36',
    rate: '540 Mbit/s', in_use: false, saved: false },
  { ssid: 'Telia-4F2A91', signal: 33, security: 'WPA2', channel: '1',
    rate: '130 Mbit/s', in_use: false, saved: false },
  { ssid: 'McDonalds Free', signal: 22, security: '', channel: '6',
    rate: '65 Mbit/s', in_use: false, saved: false },
  { ssid: '', signal: 18, security: 'WPA2', channel: '9',
    rate: '65 Mbit/s', in_use: false, saved: false },
]

let air = AIR.map((a) => ({ ...a }))

export const wifiScan = () => air.map((a) => ({ ...a }))

function joined(ssid: string): void {
  air = air.map((a) => ({ ...a, in_use: a.ssid === ssid }))
  const one = air.find((a) => a.ssid === ssid)
  net = {
    hotspot: { ...net.hotspot },
    wifi: {
      ...net.wifi, enabled: true, connected: !!one, ssid,
      signal: one?.signal ?? null, ip_address: '192.168.1.44',
    },
  }
  emit('network', networkState())
}

export function wifiConnect(ssid: string) {
  const one = air.find((a) => a.ssid === ssid)
  if (one) one.saved = true
  joined(ssid)
  return networkState()
}

export function wifiDisconnect() {
  air = air.map((a) => ({ ...a, in_use: false }))
  net = {
    hotspot: { ...net.hotspot },
    wifi: { ...net.wifi, connected: false, ssid: '', signal: null,
            ip_address: '' },
  }
  emit('network', networkState())
  return networkState()
}

export function wifiForget(ssid: string) {
  air = air.map((a) =>
    a.ssid === ssid ? { ...a, saved: false, in_use: false } : a,
  )
  if (net.wifi.ssid === ssid) return wifiDisconnect()
  emit('network', networkState())
  return networkState()
}
