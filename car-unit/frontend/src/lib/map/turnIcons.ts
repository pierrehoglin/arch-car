/* Valhalla's maneuver types, as the arrows the screens draw.

   The numbers are Valhalla's own -- see its DirectionsLeg_Maneuver_Type.
   Anything not listed is drawn as straight on, which is what an
   unrecognised instruction most often is. */

const ICONS: Record<number, string> = {
  1: 'straight', // start
  2: 'turn-right', // start right
  3: 'turn-left', // start left
  4: 'flag', // destination
  5: 'flag',
  6: 'flag',
  7: 'straight', // becomes
  8: 'straight', // continue
  9: 'slight-right',
  10: 'turn-right',
  11: 'sharp-right',
  12: 'u-turn', // U-turn right
  13: 'u-turn', // U-turn left
  14: 'sharp-left',
  15: 'turn-left',
  16: 'slight-left',
  17: 'straight', // ramp straight
  18: 'ramp-right',
  19: 'ramp-left',
  20: 'ramp-right', // exit right
  21: 'ramp-left', // exit left
  22: 'straight', // stay straight
  23: 'slight-right', // stay right
  24: 'slight-left', // stay left
  25: 'merge',
  26: 'roundabout', // enter
  27: 'roundabout', // exit
  28: 'ferry', // board
  29: 'ferry', // leave
  37: 'slight-right', // merge right
  38: 'slight-left', // merge left
}

export const turnIcon = (kind: number): string => ICONS[kind] ?? 'straight'

/** "300 m", "2.4 km", "Now" -- the distance to a turn as said on the
 *  banner. Rounded the way a driver reads it: to 10 m close up, 50 m
 *  further off. */
export function turnDistance(metres: number): string {
  if (metres < 20) return 'Now'
  if (metres < 300) return `${Math.round(metres / 10) * 10} m`
  if (metres < 1000) return `${Math.round(metres / 50) * 50} m`
  if (metres < 10_000) return `${(metres / 1000).toFixed(1)} km`
  return `${Math.round(metres / 1000)} km`
}
