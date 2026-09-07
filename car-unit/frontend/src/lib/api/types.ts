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
