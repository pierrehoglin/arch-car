import { EMPTY_RDS, type RadioState, type Station } from '../api/types'

/* The data Mirage serves.
 *
 * Taken from real readings on the unit -- these are the stations a
 * sweep in Sundsvall actually found, with the powers rtl_power
 * reported and RIX FM's own RDS. Plausible data catches layout
 * problems that round numbers hide: "Rockklassiker" against "P2" is
 * the range of name lengths the design has to survive.
 */

export interface Broadcast {
  frequency: number
  /** dB above the local noise floor. */
  power: number
  /** Empty where a peak carries no RDS -- usually noise, or a signal
   *  too weak to decode. */
  name: string
  pi: string
  radiotext?: string
  programType?: string
}

export const BROADCASTS: Broadcast[] = [
  { frequency: 92.7, power: 24.0, name: 'P3', pi: '0x2202',
    radiotext: 'Musikguiden i P3', programType: 'Pop music' },
  { frequency: 96.3, power: 14.3, name: '', pi: '' },
  { frequency: 96.9, power: 20.8, name: 'P2', pi: '0x2201',
    radiotext: 'Klassiskt på P2', programType: 'Serious classical' },
  { frequency: 99.2, power: 19.7, name: 'Mix Megapol', pi: '0xE24A',
    radiotext: 'Mix Megapol — bara hits!', programType: 'Pop music' },
  { frequency: 101.9, power: 15.2, name: 'Rockklassiker', pi: '0xE302',
    radiotext: 'Rockklassiker', programType: 'Rock music' },
  { frequency: 102.8, power: 19.7, name: 'Bandit Rock', pi: '0xE311',
    radiotext: 'Bandit Rock', programType: 'Rock music' },
  { frequency: 105.7, power: 12.4, name: 'P4 Sundsvall', pi: '0x2204',
    radiotext: 'P4 Västernorrland', programType: 'Current affairs' },
  { frequency: 107.4, power: 10.6, name: 'RIX FM', pi: '0xE241',
    radiotext: 'Bäst musik just nu!', programType: 'Pop music' },
]

export const PRESETS: Station[] = [
  { frequency: 92.7, name: 'P3' },
  { frequency: 96.9, name: 'P2' },
  { frequency: 102.8, name: 'Bandit Rock' },
  { frequency: 107.4, name: 'RIX FM' },
]

export function stateFor(frequency: number, decoded: boolean): RadioState {
  const station = BROADCASTS.find(
    (b) => Math.abs(b.frequency - frequency) < 0.05,
  )

  return {
    playing: true,
    frequency,
    name: station?.name ?? '',
    gain: 40,
    paused: false,
    node_id: 61,
    pid: 1398,
    started: Date.now() / 1000 - 300,
    rds: {
      ...EMPTY_RDS,
      /* PI arrives almost immediately; the rest takes several seconds
         of repeated groups. Serving the two separately is what makes
         the screen show a frequency before it shows a name, which is
         what actually happens. */
      pi: station?.pi ?? '',
      traffic_program: !!station?.name,
      ...(decoded && station?.name
        ? {
            ps: station.name,
            radiotext: station.radiotext ?? '',
            program_type: station.programType ?? '',
            stereo: true,
            is_music: true,
            groups: 240,
          }
        : {}),
    },
  }
}

export const INITIAL: RadioState = stateFor(107.4, true)

/* Places the geocoder can find.
 *
 * Real Swedish addresses and landmarks, spread across the country so
 * a query narrows rather than matching everything. Name lengths vary
 * on purpose: "P2" and "Gamla Uppsala kyrka" are the range a result
 * row has to survive.
 */
export interface Place {
  name: string
  road?: string
  house_number?: string
  postcode?: string
  city: string
  county: string
  latitude: number
  longitude: number
  kind: string
}

export const PLACES: Place[] = [
  { name: '', road: 'Kungsgatan', house_number: '12', postcode: '111 35',
    city: 'Stockholm', county: 'Stockholms län',
    latitude: 59.3326, longitude: 18.0649, kind: 'residential' },
  { name: '', road: 'Kungsgatan', house_number: '44', postcode: '411 15',
    city: 'Göteborg', county: 'Västra Götalands län',
    latitude: 57.7027, longitude: 11.9668, kind: 'residential' },
  { name: 'Kungsträdgården', city: 'Stockholm', county: 'Stockholms län',
    latitude: 59.3308, longitude: 18.0716, kind: 'park' },
  { name: 'Stockholms centralstation', road: 'Centralplan',
    postcode: '111 20', city: 'Stockholm', county: 'Stockholms län',
    latitude: 59.3300, longitude: 18.0587, kind: 'station' },
  { name: 'Slottsskogen', city: 'Göteborg',
    county: 'Västra Götalands län',
    latitude: 57.6889, longitude: 11.9439, kind: 'park' },
  { name: 'Ullevi', road: 'Skånegatan', city: 'Göteborg',
    county: 'Västra Götalands län',
    latitude: 57.7060, longitude: 11.9870, kind: 'stadium' },
  { name: 'Gamla Uppsala kyrka', city: 'Uppsala',
    county: 'Uppsala län',
    latitude: 59.8975, longitude: 17.6339, kind: 'church' },
  { name: 'Sundsvalls sjukhus', road: 'Lasarettsvägen',
    house_number: '21', postcode: '856 43', city: 'Sundsvall',
    county: 'Västernorrlands län',
    latitude: 62.3908, longitude: 17.2820, kind: 'hospital' },
  { name: 'Norra Berget', city: 'Sundsvall',
    county: 'Västernorrlands län',
    latitude: 62.3830, longitude: 17.3050, kind: 'viewpoint' },
  { name: '', road: 'Storgatan', house_number: '30', postcode: '852 30',
    city: 'Sundsvall', county: 'Västernorrlands län',
    latitude: 62.3903, longitude: 17.3069, kind: 'residential' },
  { name: 'Höga Kusten-bron', city: 'Kramfors',
    county: 'Västernorrlands län',
    latitude: 62.7997, longitude: 17.9375, kind: 'bridge' },
  { name: 'Åre Torg', city: 'Åre', county: 'Jämtlands län',
    latitude: 63.3986, longitude: 13.0817, kind: 'square' },
  { name: 'Ikea Sundsvall', road: 'Norrmalmsvägen', city: 'Sundsvall',
    county: 'Västernorrlands län',
    latitude: 62.4327, longitude: 17.3420, kind: 'furniture' },
  { name: 'Birsta City', city: 'Sundsvall',
    county: 'Västernorrlands län',
    latitude: 62.4355, longitude: 17.3390, kind: 'mall' },
]
