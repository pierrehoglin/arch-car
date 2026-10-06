/* Mirrors the dataclasses in carlib, field for field.
 *
 * Snake case throughout, because that is what the API sends. Renaming
 * on the way in would mean every field existing under two names, and
 * the one place a typo would go unnoticed is exactly the mapping
 * doing the renaming.
 */

export interface Rds {
  pi: string
  /** Extended country code, from group 1A. The PI's first nibble is
   *  a country code too, but a coarse one -- E covers Sweden, Spain
   *  and others -- so this is what says which country's PI table to
   *  read. Sweden is E3. Arrives later than the PI, and not from
   *  every station. */
  ecc: string
  /** An ISO country code, where a build reports that instead of the
   *  ECC. The same question answered less precisely. */
  country: string
  ps: string
  radiotext: string
  program_type: string
  alt_frequencies: number[]
  traffic_program: boolean
  /** Only meaningful together with traffic_program: a station with
   *  TA set and TP clear is signalling about bulletins elsewhere, not
   *  carrying one itself. */
  traffic_announcement: boolean
  is_music: boolean | null
  stereo: boolean | null
  /** How many RDS groups have been decoded. Climbs steadily on a good
   *  signal, so it doubles as a reception indicator. */
  groups: number
}

export interface RadioState {
  playing: boolean
  frequency: number | null
  name: string
  gain: number
  /** Muted, not stopped -- the pipeline keeps running so RDS keeps
   *  decoding and a traffic announcement is still noticed. */
  paused: boolean
  node_id: number | null
  pid: number | null
  started: number | null
  /** Where the radio would come back on. A stopped radio has no
   *  `frequency`, but it does have somewhere to return to. */
  last: number | null
  rds: Rds
}

/** A peak found while sweeping the band. */
export interface Signal {
  frequency: number
  /** dB above the local noise floor. */
  power: number
  /** Preset name, or the RDS name once identified. */
  name: string
  rds_name: string
  pi: string
}

/** Where a scan has got to. Published as `scan` events while it runs.
 *
 *  `signals` is in scan order, up the band. The first `checked` have
 *  been listened to; `current` is the one being listened to now. */
export interface ScanProgress {
  phase: 'sweeping' | 'identifying' | 'resuming' | 'done' | 'failed'
  signals: Signal[]
  checked: number
  current: number | null
  /** Unix seconds, so a screen opened mid-scan can count from it. */
  started: number
  error: string
}

export interface Station {
  frequency: number
  name: string
  /** What the station is, recorded when the preset was saved while
   *  it was playing. The PI picks its logo, so a preset carrying one
   *  can show it the moment it is tuned rather than a second later
   *  when RDS has decoded. */
  pi: string
  /** Which country's PI table applies. Sweden is E3. */
  ecc: string
  /** The same programme on other transmitters. Recorded for later;
   *  nothing reads it yet. */
  alt_frequencies: number[]
}

export const EMPTY_RDS: Rds = {
  pi: '',
  ecc: '',
  country: '',
  ps: '',
  radiotext: '',
  program_type: '',
  alt_frequencies: [],
  traffic_program: false,
  traffic_announcement: false,
  is_music: null,
  stereo: null,
  groups: 0,
}

export const EMPTY_RADIO: RadioState = {
  playing: false,
  frequency: null,
  last: null,
  name: '',
  gain: 40,
  paused: false,
  node_id: null,
  pid: null,
  started: null,
  rds: EMPTY_RDS,
}

/** A geocoded place, mirroring carlib.location.geocoding.Address. */
export interface Address {
  display_name: string
  latitude: number
  longitude: number

  name: string
  house_number: string
  road: string
  neighbourhood: string
  suburb: string
  postcode: string
  city: string
  municipality: string
  county: string
  state: string
  country: string
  country_code: string

  category: string
  kind: string
  osm_id: string
  /** node, way or relation -- an address point, an outline such as a
   *  building, or a group of them. Empty when the service did not say. */
  osm_type: string
}

/**
 * Volume, mirroring carlib.system.audio.Volume.
 *
 * `target` says which stream this is: a sink is an output -- the
 * speakers -- and a source is an input, the microphone. The same
 * shape serves both.
 */
export interface Volume {
  percent: number
  muted: boolean
  target: 'sink' | 'source'
}

/** A sink or a source on the graph. */
export interface AudioDevice {
  /** PipeWire's node id, which is what wpctl takes. It changes when
   *  the device is re-plugged, so never store it. */
  node_id: number
  name: string
  is_default: boolean
  kind: 'sink' | 'source'
  /** Its own level, read from the same wpctl line as the rest. */
  percent: number
  muted: boolean
}

/** An application producing sound. */
export interface AudioStream {
  id: number
  name: string
  application: string
  media_class: string
  state: string
  binary: string
  /** What the node calls itself, which for a Bluetooth phone is the
   *  only readable name it has. */
  description: string
  /** Null where the graph reported no level -- distinct from zero,
   *  which is a real silence. */
  percent: number | null
  muted: boolean
}

/** Everything the audio graph reports, as one reading. */
export interface AudioState {
  volume: Volume
  microphone: Volume
  devices: AudioDevice[]
  streams: AudioStream[]
}

/** A saved location, mirroring carlib.location.places.Place. */
export interface Place {
  name: string
  latitude: number
  longitude: number
  altitude: number | null
  /** Filled in by the geocoder when the place was saved. */
  address: string
  /** Only on the current position: true when the GPS has no fix yet
   *  and this is where the car last had one. */
  last_known?: boolean
  /** When a last known position was recorded, in Unix seconds. */
  at?: number | null
}

/** Reserved: wherever we are now, kept current as the car moves. */
export const CURRENT_PLACE = 'current'

/* Weather, mirroring carlib.weather.types.
 *
 * Deliberately coarse conditions: a finer set is harder to map onto
 * consistently across providers, and for a dashboard the difference
 * between light rain and rain is not worth a wrong icon.
 */
export type Condition =
  | 'clear'
  | 'partly-cloudy'
  | 'cloudy'
  | 'fog'
  | 'drizzle'
  | 'rain'
  | 'sleet'
  | 'snow'
  | 'thunder'
  | 'unknown'

export interface Conditions {
  /** ISO 8601, as the API sends it. */
  time: string | null

  temperature: number | null
  feels_like: number | null
  /** The forecast's own uncertainty, from the 10th and 90th
   *  percentiles -- not a high and a low over a period. */
  temperature_p10: number | null
  temperature_p90: number | null
  /** Actual extremes, for an entry covering a period. */
  temperature_high: number | null
  temperature_low: number | null

  humidity: number | null
  pressure: number | null
  dew_point: number | null

  wind_speed: number | null
  wind_gust: number | null
  wind_direction: number | null
  wind_speed_p10: number | null
  wind_speed_p90: number | null

  cloud_cover: number | null
  cloud_low: number | null
  cloud_medium: number | null
  cloud_high: number | null

  uv_index: number | null
  /** Metres. Reported by OpenWeather, not by MET. */
  visibility: number | null

  precipitation: number
  precipitation_probability: number | null

  condition: Condition
  symbol: string
  /** Hours this entry covers. 0 for an instantaneous reading. */
  period_hours: number
}

export interface Day {
  /** ISO date. */
  date: string | null
  high: number | null
  low: number | null
  precipitation: number
  wind_max: number | null
  condition: Condition
  /** How many hourly entries went into it, so a partial day can say
   *  so rather than looking like a quiet one. */
  entries: number
}

export interface Forecast {
  provider: string
  latitude: number
  longitude: number
  altitude: number | null
  updated: string | null
  expires: string | null
  current: Conditions | null
  hourly: Conditions[]
  daily: Day[]
  /** Where this is the weather for. */
  place: string
}

/* Bluetooth, mirroring what the daemon's /api/bluetooth returns. */

export interface BtAdapter {
  path: string
  address: string
  name: string
  powered: boolean
  discoverable: boolean
  pairable: boolean
  discovering: boolean
  /** Whether bluetooth.service is running. On and off is the service,
   *  not the radio. */
  service_active: boolean
}

export interface BtDevice {
  path: string
  address: string
  name: string
  /** BlueZ's own icon name: phone, audio-headset, computer. */
  icon: string
  connected: boolean
  paired: boolean
  trusted: boolean
  /** Signal strength while discovering; absent once out of range. */
  rssi: number | null
  battery: number | null
  uuids: string[]
}

/** How long the car is findable and scanning. */
export interface BtWindow {
  open: boolean
  seconds_left: number
}

/** A pairing the car started, and how it went. */
export interface BtAttempt {
  address: string
  state: 'pairing' | 'paired' | 'failed'
  error: string
}

export interface BtState {
  adapter: BtAdapter
  devices: BtDevice[]
  window: BtWindow
  attempt: BtAttempt | null
}

/** A pairing waiting for someone to confirm it. */
export interface PairingRequest {
  device: string
  address: string
  name: string
  /** Six digits to compare with the phone. Absent for Just Works,
   *  where there is only a yes or no to give. */
  passkey: string | null
  kind: 'confirm' | 'authorize'
}

/* What a source is playing.
 *
 * One shape for both transports: AVRCP and MPRIS carry the same
 * things under different names. AVRCP has no artwork -- the profile
 * can carry it, but BlueZ does not expose it -- and neither has a
 * queue.
 */
export interface NowPlaying {
  source: string
  /** The phone's name over Bluetooth, the player's over MPRIS. */
  device: string
  status: 'playing' | 'paused' | 'stopped' | ''
  title: string
  artist: string
  album: string
  /** Milliseconds, both. */
  duration: number | null
  position: number | null
  /** A URL on the provider's CDN, or empty. */
  art: string
  track_id: string
  /** Whether the position can be set. MPRIS can; AVRCP cannot, so a
   *  Bluetooth slider is a readout rather than a control. */
  seekable: boolean
  /** Whether there is a player at all. A phone that has not started
   *  anything is the ordinary state, not an error. */
  present: boolean
}


/* The radio. Wi-Fi and the hotspot share one interface, so they are
 * reported together -- a screen showing a fresh one beside a stale
 * one would be showing an impossible state.
 */

export interface WifiState {
  enabled: boolean
  connected: boolean
  ssid: string
  /** 0 to 100, or null when not associated. */
  signal: number | null
  ip_address: string
  device: string
}

export interface HotspotState {
  active: boolean
  ssid: string
  channel: number | null
  band: string
  interface: string
  address: string
  /** Which connection the hotspot shares out. */
  uplink: string
  clients: unknown[]
}

/** A network in range. */
export interface WifiNetwork {
  ssid: string
  /** 0 to 100. */
  signal: number
  /** Empty or '--' for an open network. */
  security: string
  channel: string
  rate: string
  /** Whether this is the one currently joined. */
  in_use: boolean
  /** Whether there is a profile for it, so no password is needed. */
  saved: boolean
}

export interface NetworkState {
  wifi: WifiState
  hotspot: HotspotState
  /** SSIDs with a stored profile, whether or not they are in range.
   *  Reported with the status so the list has something to show
   *  before a scan has finished. */
  saved: string[]
}

/** The two positions the one radio has. The car is either on a
 *  network or serving one; there is no off. */
export type NetworkMode = 'wifi' | 'hotspot'


/* The phone's books.
 *
 * PBAP serves several through one interface: the address book, the
 * favourites, and the call logs. They are cached separately, because
 * they go stale at very different rates -- an address book is good
 * for weeks, a list of recent calls for minutes.
 */

export type BookName = 'pb' | 'fav' | 'cch' | 'ich' | 'och' | 'mch'

export interface PhoneNumber {
  number: string
  /** cell, home, work -- as the vCard labelled it. */
  type: string
}

export interface Contact {
  name: string
  numbers: PhoneNumber[]
  emails: string[]
  /** For call-log entries: received, dialed or missed. Null on an
   *  ordinary contact, which is most of them. */
  call_type: string | null
  /** ISO 8601, for call-log entries. */
  call_time: string | null
}

export interface Book {
  address: string
  book: BookName
  contacts: Contact[]
  /** Unix seconds, or 0 for a book never pulled. */
  fetched: number
  /** Old enough to be worth refreshing. Weeks for contacts, minutes
   *  for a call log. */
  stale: boolean
  /** Whether a sync could work: the phone connected and offering
   *  PBAP. False means do not try rather than try and wait. */
  available: boolean
}

/** Where the car is, and what that is based on.
 *
 *  gps   a live fix
 *  last  no fix now; where the car last had one (`at` says when)
 *  pin   location.latitude/longitude are set and the GPS is ignored
 *  none  nothing known at all -- the other fields are absent */
export interface Position {
  source: 'gps' | 'last' | 'pin' | 'none'
  latitude?: number
  longitude?: number
  altitude?: number | null
  speed_kmh?: number | null
  /** Degrees clockwise from true north. Only meaningful moving: a
   *  parked GPS reports whatever direction the noise suggests. */
  heading?: number | null
  hdop?: number | null
  satellites?: number
  /** Unix seconds of the reading. Null for a pin. */
  at?: number | null
}
