import { addProtocol, setWorkerUrl, type StyleSpecification } from 'maplibre-gl'
import { Protocol } from 'pmtiles'
/* MapLibre's worker, bundled by Vite into one self-contained file.
 *
 * MapLibre finds its worker next to its own module by default. In
 * the single-file build there is no such file -- the library is
 * inlined into index.html -- so it asked for /map/maplibre-gl-
 * worker.mjs and got a 404, and the map never loaded. The worker also
 * imports a shared chunk by relative path, so it cannot simply be
 * inlined as it is: `?worker&url` has Vite bundle it with everything
 * it imports and hand back where it put it. */
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { layers, namedFlavor } from '@protomaps/basemaps'
import { TILES_PATH } from '../api/map'

/* The map's look, built from the Protomaps basemap layers rather
 * than a style file: the flavour follows the panel's theme, and the
 * labels are asked for in Swedish where the data has them.
 *
 * Glyphs (label fonts) and sprites (icons) still come from the
 * Protomaps CDN. The tiles are offline; the labels are not yet, and
 * without signal the map draws with no text on it. Bundling them is
 * a separate step -- the font set alone is several megabytes. */

const SOURCE = 'protomaps'

const GLYPHS =
  'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf'

const SPRITES = 'https://protomaps.github.io/basemaps-assets/sprites/v4'

let registered = false

/** Point MapLibre at its worker and teach it `pmtiles://` URLs. Once
 *  per page: both are global, and registering twice throws. */
export function registerProtocol(): void {
  if (registered) return
  setWorkerUrl(workerUrl)
  const protocol = new Protocol()
  addProtocol('pmtiles', protocol.tile)
  registered = true
}

export function mapStyle(dark: boolean): StyleSpecification {
  const flavor = dark ? 'dark' : 'light'

  return {
    version: 8,
    glyphs: GLYPHS,
    sprite: `${SPRITES}/${flavor}`,
    sources: {
      [SOURCE]: {
        type: 'vector',
        url: `pmtiles://${location.origin}${TILES_PATH}`,
      },
    },
    layers: layers(SOURCE, namedFlavor(flavor), { lang: 'sv' }),
  }
}
