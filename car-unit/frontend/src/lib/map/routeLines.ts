import type {
  GeoJSONSource,
  LngLatBoundsLike,
  Map as MapLibre,
} from 'maplibre-gl'
import type { RouteOption } from '../api/navigation'

/* The route on the map: the chosen way in the accent with a dark
   casing, and the alternatives in grey beside it.

   One GeoJSON source, three layers told apart by a `chosen` property,
   so switching between the options is new data rather than new layers.

   Added below the first label layer, so street names stay readable on
   top of the line. And added again after every style change: a Day or
   Night switch replaces the style, and anything not in it -- this --
   goes with the old one. */

const SOURCE = 'trip'

/** The grey lines, for tapping one to choose it. */
export const ALTERNATIVES = 'trip-alternatives'
const CASING = 'trip-casing'
const LINE = 'trip-line'

/** MapLibre paints with colours, not CSS variables, so the theme's
 *  are read off an element inside the map -- the accent can be set on
 *  any ancestor, and this finds whichever is in force. */
function colours(element: HTMLElement) {
  const style = getComputedStyle(element)
  const read = (name: string, fallback: string) =>
    style.getPropertyValue(name).trim() || fallback
  return {
    accent: read('--accent', '#d8b146'),
    alternative: read('--text-faint', '#7d8487'),
    /* Dark in both themes. The page background would be the obvious
       choice, but by day it is as pale as the map, and the line lost
       its edge against it. */
    casing: 'rgba(0, 0, 0, 0.55)',
  }
}

function ensure(map: MapLibre): void {
  if (map.getSource(SOURCE)) return

  map.addSource(SOURCE, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })

  const labels = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
  const round = { 'line-join': 'round', 'line-cap': 'round' } as const

  map.addLayer(
    {
      id: ALTERNATIVES,
      type: 'line',
      source: SOURCE,
      filter: ['==', ['get', 'chosen'], false],
      layout: round,
      paint: { 'line-width': 7, 'line-opacity': 0.85 },
    },
    labels,
  )
  map.addLayer(
    {
      id: CASING,
      type: 'line',
      source: SOURCE,
      filter: ['==', ['get', 'chosen'], true],
      layout: round,
      paint: { 'line-width': 11 },
    },
    labels,
  )
  map.addLayer(
    {
      id: LINE,
      type: 'line',
      source: SOURCE,
      filter: ['==', ['get', 'chosen'], true],
      layout: round,
      paint: { 'line-width': 7 },
    },
    labels,
  )
}

/**
 * Draw the options, the chosen one on top. Empty to clear.
 *
 * Safe to call at any time after the style has loaded, as often as
 * wanted: the layers are created when missing and the colours are
 * read afresh, so a theme change is picked up by calling it again.
 */
export function drawRoutes(
  map: MapLibre,
  element: HTMLElement,
  options: RouteOption[],
  chosen: number,
): void {
  ensure(map)

  const paint = colours(element)
  map.setPaintProperty(ALTERNATIVES, 'line-color', paint.alternative)
  map.setPaintProperty(CASING, 'line-color', paint.casing)
  map.setPaintProperty(LINE, 'line-color', paint.accent)

  /* The chosen one last, so where lines overlap it is the one seen. */
  const order = options
    .map((option, index) => ({ option, index }))
    .sort((a, b) => Number(a.index === chosen) - Number(b.index === chosen))

  const source = map.getSource(SOURCE) as GeoJSONSource
  source.setData({
    type: 'FeatureCollection',
    features: order.map(({ option, index }) => ({
      type: 'Feature',
      properties: { index, chosen: index === chosen },
      geometry: { type: 'LineString', coordinates: option.shape },
    })),
  })
}

/** The box around a route and anything else that should be in view. */
export function boundsOf(
  shape: [number, number][],
  extra: [number, number][] = [],
): LngLatBoundsLike | null {
  const all = [...shape, ...extra]
  if (!all.length) return null
  let [west, south] = all[0]
  let [east, north] = all[0]
  for (const [lon, lat] of all) {
    west = Math.min(west, lon)
    east = Math.max(east, lon)
    south = Math.min(south, lat)
    north = Math.max(north, lat)
  }
  return [
    [west, south],
    [east, north],
  ]
}
