import { Marker, type Map as MapLibre } from 'maplibre-gl'
import type { Waypoint } from '../route.svelte'

/* The route's destination and stops on the map.

   Plain elements made here rather than Svelte components: there are
   as many stops as have been added, and they are rebuilt whenever the
   route changes, which is a list to recreate rather than a component
   to keep. Their colours are CSS variables, so they follow the theme
   like everything else on the map.

   The destination is a flag, the stops numbered circles -- neither
   can be mistaken for the pin, which is still free to be tapped
   around while a route is shown. */

const FLAG = `
<svg viewBox="0 0 36 44" width="36" height="44" aria-hidden="true"
     style="display:block;overflow:visible;filter:drop-shadow(0 2px 3px rgb(0 0 0 / .45))">
  <rect x="5" y="3" width="3.5" height="40" rx="1.5" fill="#fff"/>
  <path d="M8 4 H31 L26 12.5 L31 21 H8 Z" fill="var(--accent)"
        stroke="#fff" stroke-width="2" stroke-linejoin="round"/>
</svg>`

function flag(title: string): HTMLElement {
  const element = document.createElement('div')
  element.setAttribute('role', 'img')
  element.setAttribute('aria-label', `Destination: ${title}`)
  element.innerHTML = FLAG
  return element
}

function stop(number: number, title: string): HTMLElement {
  const element = document.createElement('div')
  element.setAttribute('role', 'img')
  element.setAttribute('aria-label', `Stop ${number}: ${title}`)
  element.textContent = String(number)
  Object.assign(element.style, {
    display: 'grid',
    placeItems: 'center',
    width: '28px',
    height: '28px',
    fontFamily: 'var(--font-display)',
    fontSize: '14px',
    fontWeight: '700',
    color: 'var(--accent-ink)',
    background: 'var(--accent)',
    border: '2.5px solid #fff',
    borderRadius: '50%',
    boxShadow: '0 1px 3px rgb(0 0 0 / .45)',
  })
  return element
}

export class TripMarkers {
  private markers: Marker[] = []

  constructor(private readonly map: MapLibre) {}

  /** Show these, and nothing else. */
  update(destination: Waypoint | null, stops: Waypoint[]): void {
    this.clear()
    if (!destination) return

    stops.forEach((place, index) => {
      this.markers.push(
        new Marker({ element: stop(index + 1, place.title) })
          .setLngLat([place.longitude, place.latitude])
          .addTo(this.map),
      )
    })

    /* The pole's foot on the spot. The flag flies to the right of it,
       so the anchor is bottom left, nudged in by the pole's offset. */
    this.markers.push(
      new Marker({
        element: flag(destination.title),
        anchor: 'bottom-left',
        offset: [-7, 0],
      })
        .setLngLat([destination.longitude, destination.latitude])
        .addTo(this.map),
    )
  }

  clear(): void {
    for (const marker of this.markers) marker.remove()
    this.markers = []
  }
}
