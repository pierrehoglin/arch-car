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
