<script lang="ts">
  import Icon from '$lib/Icon.svelte'

  /* The map itself is not here yet. This is the chrome that sits over
     it -- search, speed, and the controls -- so the layout is settled
     before MapLibre and the pmtiles archive are wired in. */

  let query = $state('')
  const speed = 40
</script>

<div class="map">
  <div class="surface" aria-hidden="true">
    <p class="pending">Map</p>
  </div>

  <form class="search" onsubmit={(e) => e.preventDefault()}>
    <input
      type="search"
      placeholder="Search places..."
      bind:value={query}
      aria-label="Search places"
    />
    <button class="go" disabled={!query.trim()}>Go</button>
  </form>

  <div class="speed">
    <span class="figure">{speed}</span>
    <span class="unit">km/h</span>
  </div>

  <div class="controls">
    <button class="control primary" aria-label="Centre on position">
      <Icon name="crosshair" size={22} />
    </button>
    <button class="control" aria-label="Reset bearing">
      <Icon name="compass" size={22} />
    </button>
    <button class="control" aria-label="Zoom out">
      <Icon name="remove" size={22} />
    </button>
  </div>

  <p class="attribution">© OpenStreetMap contributors</p>
</div>

<style>
  .map {
    position: relative;
    height: 100%;
    overflow: hidden;
  }

  /* Stand-in for the map canvas. Deliberately plain -- a fake street
     grid would only be mistaken for the real thing in a screenshot. */
  .surface {
    display: grid;
    place-items: center;
    height: 100%;
    background: var(--panel-2);
  }

  .pending {
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  /* Everything below floats over the map, so each piece carries its
     own background rather than relying on the surface behind it. */
  .search {
    position: absolute;
    top: 18px;
    left: 18px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .search input {
    width: 380px;
    height: 46px;
    padding: 0 18px;
    font: inherit;
    font-size: 16px;
    color: var(--text);
    background: color-mix(in srgb, var(--bar) 88%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .search input::placeholder {
    color: var(--text-faint);
  }

  .search input:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }

  .go {
    height: 46px;
    padding: 0 22px;
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--accent-ink);
    background: var(--accent);
    border: 0;
    border-radius: var(--radius-sm);
  }

  .go:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .speed {
    position: absolute;
    top: 18px;
    right: 22px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1;
  }

  .figure {
    font-family: var(--font-display);
    font-size: 34px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    /* Full brightness even under Night Panel: this is the readout the
       mode exists to keep legible. */
    color: var(--text);
  }

  .unit {
    margin-top: 2px;
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  .controls {
    position: absolute;
    right: 22px;
    bottom: 28px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .control {
    display: grid;
    place-items: center;
    width: 54px;
    height: 54px;
    color: var(--text);
    background: color-mix(in srgb, var(--bar) 88%, transparent);
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  /* Recentring is the one control pressed while driving, so it is
     the only one that carries the accent. */
  .control.primary {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: transparent;
  }

  .control:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Required by the ODbL licence the map data is under. */
  .attribution {
    position: absolute;
    right: 10px;
    bottom: 6px;
    margin: 0;
    font-size: 11px;
    color: var(--text-faint);
  }
</style>
