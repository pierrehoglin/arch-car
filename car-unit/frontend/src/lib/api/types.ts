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
