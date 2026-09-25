/* Swedish stations, by RDS programme reference.
 *
 * A Swedish PI code is four hex digits: `E`, then a coverage-area
 * nibble, then two digits identifying the programme. SR P1 is E201
 * in one region and E001 in another -- the station is the same, the
 * transmitter area is not. So the key is the last two digits, and
 * matching the whole code would work at home and fail in the next
 * county.
 *
 * `redsea` decodes the PI within a second of tuning, well before the
 * station name arrives in PS, which is what makes this worth having:
 * the screen can say "SR P3" while RDS is still assembling the rest.
 */

/** The two hex digits that identify the station, or '' if not ours. */
export function referenceOf(pi: string): string {
  /* redsea writes the code as `0xE201`, which is how it appears all
     the way through to here. Stripping the prefix rather than
     expecting one either way: a bare `E201` is just as valid a thing
     to be handed, and the number is the same. */
  const code = pi.trim().toUpperCase().replace(/^0X/, '')

  // Four hex digits beginning with E. Anything else is another
  // country, a decoding error, or nothing yet.
  if (!/^E[0-9A-F]{3}$/.test(code)) return ''
  return code.slice(2)
}

/* Everything the published PI table lists a name for. Gaps in the
   table are allocations nobody is using, and are left out rather
   than filled with placeholders. */
const NAMES: Record<string, string> = {
  '01': 'SR P1',
  '02': 'SR P2',
  '03': 'SR P3',
  '05': 'Malmökanalen',
  '07': 'SR Finska',
  '09': 'SR P3 Din Gata',
  '0B': 'SR Barn',
  '20': 'NRJ',
  '24': 'SR P4',
  '2A': 'Radio Nostalgi',
  '35': 'SR P6',
  '37': 'Radio Hope Södertälje',
  '38': 'Radio Hope Göteborg',
  '3A': 'Radio Lidköping',
  '40': 'Radio Trollhättan',
  '41': 'RIX FM',
  '43': 'Mix Megapol',
  '44': 'Lugna Favoriter',
  '45': 'STAR FM',
  '51': 'Disco 54',
  '52': 'Bandit Classic',
  '53': 'Go Country',
  '54': "HitMix 90's",
  '55': 'Sonic',
  '56': 'RIX FM Fresh',
  '58': 'Stockholm Närradio 88,0',
  '5F': 'Stockholm Närradio 95,3',
  '65': 'Stockholm Närradio 101,1',
  '78': 'Guldkanalen',
  '79': 'Dansbandskanalen',
  '80': 'Örkelljunga Närradio',
  '88': 'Radio Fryksdalen',
  '90': 'Retro FM',
  '91': 'Radio Topp 40',
  '92': 'Relax FM',
  '93': 'Radio Yalla',
  '94': 'Rock FM',
  '97': 'Radio Active',
  '9E': 'Skärgårdsradion',
  A0: 'Rockklassiker',
  A4: 'Power Hit Radio',
  A6: 'Sportsnack',
  A7: 'Bandit Rock',
  A8: 'Vinyl FM',
  A9: 'Svensk Pop',
  AB: 'Radio Aftonbladet',
  B8: 'Gold FM',
  BA: 'Radio Båstad',
  BD: 'Radio Tyresö',
  C1: 'Radio Alingsås',
  C6: 'Radio Treby',
  C7: 'Radio Bohuslän',
  C8: 'GNF 103,1',
  C9: 'GNF 102,6',
  CA: 'GNF 94,9',
  CC: 'Radio Sydväst',
  D1: 'Lugna Klassiker',
  D5: 'Radiosol',
  D6: 'Radio Krokom',
  E0: 'Radio 45',
  EE: 'Puls FM',
  F1: 'Nostalgi',
  FA: 'Lite FM',
  FB: 'Pirate Rock',
  FC: 'Radio Gold',
}

/* Logos, picked up from the folder rather than listed here.
 *
 * Drop `bandit-rock-A7.png` in and Bandit Rock has a logo; nothing
 * else to edit, and no build failure for the ones that are missing.
 *
 * The reference is the last two characters before the extension, and
 * whatever comes before it is for whoever is looking at the folder --
 * `A7.png` says nothing about which station it is, and a folder of
 * those is unreadable.
 *
 * `-dark-` just before the reference marks a version for the dark
 * panels: `bandit-rock-dark-A7.png`. Optional, and only ever an
 * override -- a station with one file uses it on both.
 *
 * SVG or PNG. SVG is better where there is one -- sharp at any size,
 * usually smaller -- so it wins if a station has both, rather than
 * leaving it to whichever the glob happened to list last.
 */
const LOGOS = import.meta.glob<string>('./assets/stations/*.{svg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
})

interface Named {
  /** The two hex digits, or '' if the name carries none. */
  reference: string
  /** Which panel it is for. */
  variant: 'light' | 'dark'
}

/** What a logo filename says about itself. */
export function readName(path: string): Named {
  const file = (path.split('/').pop() ?? '').replace(/\.(svg|png)$/i, '')
  const parts = file.split('-')

  const reference = (parts.at(-1) ?? '').toUpperCase()
  if (!/^[0-9A-F]{2}$/.test(reference)) {
    return { reference: '', variant: 'light' }
  }

  /* The segment before the reference, so `dark` reads as a marker
     rather than part of the name. A station called something ending
     in "dark" would need a hyphen elsewhere, which is a problem
     nobody has. */
  const variant = (parts.at(-2) ?? '').toLowerCase() === 'dark'
    ? 'dark'
    : 'light'

  return { reference, variant }
}

const isVector = (path: string) => /\.svg$/i.test(path)

interface Pair {
  light: string
  dark: string
}

const logoFiles: Record<string, Pair> = {}
const logoPaths: Record<string, Pair> = {}

for (const [path, url] of Object.entries(LOGOS)) {
  const { reference, variant } = readName(path)

  if (!reference) {
    /* Named wrongly, so it can never be found. Said out loud rather
       than skipped quietly: a logo that silently does nothing is a
       thing you stare at the screen about. */
    console.warn(
      `station logo ignored: ${path} does not end in a two-digit ` +
        'PI reference, e.g. bandit-rock-A7.png',
    )
    continue
  }

  logoFiles[reference] ??= { light: '', dark: '' }
  logoPaths[reference] ??= { light: '', dark: '' }

  const held = logoPaths[reference][variant]

  /* Two files for one station and one panel. Keep the vector and
     say so: the other will never be drawn, and finding that out by
     editing a PNG nothing reads is a bad afternoon. */
  if (held) {
    const keepNew = isVector(path) && !isVector(held)
    console.warn(
      `two ${variant} logos for ${reference}: using ` +
        `${keepNew ? path : held}, ignoring ${keepNew ? held : path}`,
    )
    if (!keepNew) continue
  }

  logoFiles[reference][variant] = url
  logoPaths[reference][variant] = path
}

/** The station's name from its PI code, or '' if unknown. */
export const nameForPi = (pi: string): string =>
  NAMES[referenceOf(pi)] ?? ''

/**
 * Its logo for the panel in use, or '' where there is no file.
 *
 * A dark panel falls back to the light file, because one logo that
 * suits both is the normal case and having to copy it under a second
 * name would be busywork.
 *
 * A light panel does not fall back the other way. A logo drawn for a
 * dark panel is pale, and pale on the day theme is a blank space
 * where the frequency used to be -- worse than no logo, which at
 * least leaves the number.
 */
export function logoForPi(pi: string, dark: boolean): string {
  const pair = logoFiles[referenceOf(pi)]
  if (!pair) return ''

  return dark ? pair.dark || pair.light : pair.light
}
