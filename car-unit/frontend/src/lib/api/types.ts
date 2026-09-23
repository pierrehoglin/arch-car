/* Mirrors the dataclasses in carlib, field for field.
 *
 * Snake case throughout, because that is what the API sends. Renaming
 * on the way in would mean every field existing under two names, and
 * the one place a typo would go unnoticed is exactly the mapping
 * doing the renaming.
 */

export interface Rds {
  pi: string
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

export interface Station {
  frequency: number
  name: string
}

export const EMPTY_RDS: Rds = {
  pi: '',
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

/** A saved location, mirroring carlib.location.places.Place. */
export interface Place {
  name: string
  latitude: number
  longitude: number
  altitude: number | null
  /** Filled in by the geocoder when the place was saved. */
  address: string
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
