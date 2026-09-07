import {
  EMPTY_RDS,
  type Condition,
  type Conditions,
  type Day,
  type Forecast,
  type RadioState,
  type Station,
} from '../api/types'

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


/* Weather.
 *
 * Built rather than listed, so the hourly run is long enough to
 * scroll and the days are plausible against each other. A September
 * evening in Stockholm: overcast, cooling overnight, rain coming in.
 */

const HOURLY_HOURS = 48
const DAYS = 7

function conditionAt(hour: number): Condition {
  const cycle = hour % 24
  if (hour > 30) return 'rain'
  if (cycle >= 2 && cycle < 6) return 'fog'
  if (cycle >= 10 && cycle < 16) return 'partly-cloudy'
  return 'cloudy'
}

/** A smooth day/night curve, coolest before dawn. */
function temperatureAt(hour: number, from: Date): number {
  const clock = (from.getHours() + hour) % 24
  const swing = Math.cos(((clock - 14) / 24) * 2 * Math.PI)
  const drift = -hour * 0.02
  return Math.round((13 + swing * 4 + drift) * 10) / 10
}

function hourly(from: Date): Conditions[] {
  return Array.from({ length: HOURLY_HOURS }, (_, hour) => {
    const time = new Date(from)
    time.setHours(from.getHours() + hour, 0, 0, 0)

    const condition = conditionAt(hour)
    const wet = condition === 'rain'
    const temperature = temperatureAt(hour, from)

    return {
      time: time.toISOString(),
      temperature,
      feels_like: Math.round((temperature - 1.2) * 10) / 10,
      temperature_p10: temperature - 1.5,
      temperature_p90: temperature + 1.5,
      temperature_high: null,
      temperature_low: null,
      humidity: wet ? 92 : 71 + (hour % 5),
      pressure: 1002 - Math.round(hour / 12),
      dew_point: Math.round((temperature - 3) * 10) / 10,
      wind_speed: Math.round((2.5 + (hour % 7) * 0.4) * 10) / 10,
      wind_gust: Math.round((5 + (hour % 7) * 0.8) * 10) / 10,
      wind_direction: (200 + hour * 4) % 360,
      wind_speed_p10: null,
      wind_speed_p90: null,
      cloud_cover: condition === 'partly-cloudy' ? 45 : 99,
      cloud_low: 60,
      cloud_medium: 30,
      cloud_high: 10,
      uv_index: 0,
      visibility: condition === 'fog' ? 800 : 10_000,
      precipitation: wet ? 0.6 : 0,
      precipitation_probability: wet ? 70 : 0,
      condition,
      symbol: condition,
      period_hours: 1,
    } satisfies Conditions
  })
}

function daily(from: Date): Day[] {
  const shape: { condition: Condition; high: number; low: number;
                 rain: number; chance: number }[] = [
    { condition: 'rain', high: 18, low: 11, rain: 4.2, chance: 55 },
    { condition: 'clear', high: 19, low: 10, rain: 0, chance: 23 },
    { condition: 'rain', high: 17, low: 11, rain: 6.1, chance: 43 },
    { condition: 'cloudy', high: 15, low: 9, rain: 0.4, chance: 18 },
    { condition: 'partly-cloudy', high: 16, low: 8, rain: 0, chance: 12 },
    { condition: 'thunder', high: 17, low: 12, rain: 9.4, chance: 68 },
    { condition: 'drizzle', high: 14, low: 9, rain: 1.8, chance: 35 },
  ]

  return Array.from({ length: DAYS }, (_, index) => {
    const date = new Date(from)
    date.setDate(from.getDate() + index)

    const day = shape[index % shape.length]
    return {
      date: date.toISOString().slice(0, 10),
      high: day.high,
      low: day.low,
      precipitation: day.rain,
      wind_max: 8 + index,
      condition: day.condition,
      /* The first day is partial: the hours before now are gone, and
         a screen should be able to say so. */
      entries: index === 0 ? 24 - from.getHours() : 24,
    } satisfies Day
  })
}

/* Places that have been saved on the unit. "current" is not among
   them: it is reserved, and resolves to wherever the car is. */
export const SAVED_PLACES = [
  {
    name: 'home',
    latitude: 62.3908,
    longitude: 17.3069,
    altitude: 12,
    address: 'Storgatan 30, Sundsvall',
  },
  {
    name: 'work',
    latitude: 59.3326,
    longitude: 18.0649,
    altitude: 28,
    address: 'Kungsgatan 12, Stockholm',
  },
  {
    name: 'stugan',
    latitude: 63.3986,
    longitude: 13.0817,
    altitude: 380,
    address: 'Åre Torg, Åre',
  },
]

/* Somewhere warmer, somewhere colder, so switching place visibly
   changes the numbers rather than looking like nothing happened. */
const OFFSETS: Record<string, number> = {
  current: 0,
  home: -2.5,
  work: 0.5,
  stugan: -6,
}

const NAMES: Record<string, string> = {
  current: 'Stockholms kommun',
  home: 'Sundsvalls kommun',
  work: 'Stockholms kommun',
  stugan: 'Åre kommun',
}

export function makeForecast(place = 'current'): Forecast {
  const from = new Date()
  from.setMinutes(0, 0, 0)

  const offset = OFFSETS[place] ?? 0
  const shift = (value: number | null) =>
    value === null ? null : Math.round((value + offset) * 10) / 10

  const hours = hourly(from).map((hour) => ({
    ...hour,
    temperature: shift(hour.temperature),
    feels_like: shift(hour.feels_like),
    dew_point: shift(hour.dew_point),
  }))

  const now: Conditions = { ...hours[0], period_hours: 0 }
  const saved = SAVED_PLACES.find((p) => p.name === place)

  return {
    provider: 'metno',
    latitude: saved?.latitude ?? 59.3293,
    longitude: saved?.longitude ?? 18.0686,
    altitude: saved?.altitude ?? 28,
    updated: new Date().toISOString(),
    expires: new Date(Date.now() + 30 * 60_000).toISOString(),
    current: now,
    hourly: hours,
    daily: daily(from).map((day) => ({
      ...day,
      high: day.high === null ? null : Math.round(day.high + offset),
      low: day.low === null ? null : Math.round(day.low + offset),
    })),
    place: NAMES[place] ?? place,
  }
}
