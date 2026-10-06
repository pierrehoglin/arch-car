<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Button from '$lib/ui/Button.svelte'
  import WeatherDialog from '$lib/ui/WeatherDialog.svelte'
  import { iconFor, nameFor, watch, weather } from '$lib/weather.svelte'
  import { coverFor } from '$lib/covers'
  import { logoForPi, nameForPi } from '$lib/stations'
  import { isDark } from '$lib/settings.svelte'
  import CarMap from '$lib/map/CarMap.svelte'
  import TurnBanner from '$lib/map/TurnBanner.svelte'
  import { nav, turnShown } from '$lib/navigation.svelte'
  import type { CarLook, CarMapStatus } from '$lib/map/car'
  import { position, speedOf } from '$lib/position.svelte'
  import {
    here as carPlace,
    refresh as refreshPlace,
    watch as watchPlace,
  } from '$lib/place.svelte'
  import {
    radio,
    refresh as refreshRadio,
    seek as seekRadio,
    toggle as toggleRadio,
    watch as watchRadio,
  } from '$lib/radio.svelte'
  import {
    busyWith,
    command,
    current as nowPlaying,
    toggle,
    watch as watchMedia,
  } from '$lib/media.svelte'

  /* The clock and greeting are local. The weather comes from the
     daemon; the media tile is still placeholder. */

  let now = $state(new Date())

  $effect(() => {
    const timer = setInterval(() => (now = new Date()), 10_000)
    return () => clearInterval(timer)
  })

  const clock = $derived(
    now.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' }),
  )

  const date = $derived(
    now.toLocaleDateString('en-GB', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    }),
  )

  /* Split at 12 and 18 rather than by daylight: the greeting is about
     the working day, not the sun, and in a Swedish winter those come
     apart badly. */
  const greeting = $derived(
    now.getHours() < 12
      ? 'Good morning'
      : now.getHours() < 18
        ? 'Good afternoon'
        : 'Good evening',
  )

  let forecastOpen = $state(false)

  $effect(() => watch())

  /* Always where the car is. The forecast dialog can look at a saved
     place, but that is its own choice and never shows up here. */
  const forecast = $derived(weather.here)

  /* Where the car is, by address -- street, postcode and town -- from
     the daemon's 'place' event, so it changes as soon as the address
     does rather than with the weather. Fetched once on opening, which
     is also what has an address looked up when there is none. */
  $effect(() => {
    refreshPlace()
    return watchPlace()
  })

  /** The address in two lines, as it is written on an envelope:
   *  street, then postcode and town. The forecast's town alone until
   *  there is an address. */
  const placeLines = $derived.by((): [string, string] => {
    const parts = carPlace.place?.details
    if (!parts) return [carPlace.place?.address || forecast?.place || '', '']

    const street =
      parts.name ||
      [parts.road, parts.house_number].filter(Boolean).join(' ')
    /* The daemon's own order for the town: the most useful
       settlement name the address has. */
    const town =
      parts.city || parts.municipality || parts.suburb || parts.county
    const postal = [parts.postcode, town].filter(Boolean).join(' ')

    /* A motorway between towns has no street to speak of; the town
       then goes on the first line rather than leaving it empty. */
    return street ? [street, postal] : [postal, '']
  })
  const current = $derived(forecast?.current)
  const condition = $derived(current?.condition ?? 'unknown')
  const temperature = $derived(
    typeof current?.temperature === 'number'
      ? Math.round(current.temperature)
      : '—',
  )

  /* Watched here rather than in the root layout: the clock it starts
     is only worth running while something is showing elapsed time,
     and nothing on this screen does. */
  $effect(() => watchMedia())

  const track = $derived(nowPlaying())

  /* Ours for Bluetooth, which never sends any. Everything that shows
     artwork goes through this, so the two screens cannot end up
     disagreeing about when there is a picture. */
  /* The radio, which the media store knows nothing about -- it is
     not a player on any bus. Watched here so the tile can show it
     without opening the FM screen. */
  $effect(() => {
    refreshRadio()
    return watchRadio()
  })

  const rds = $derived(radio.state.rds)

  /* On air, not merely running: a paused radio is silent, and the
     tile should be offering whatever else there is. */
  const onAir = $derived(radio.state.playing && !radio.state.paused)

  /* Nothing behind the station.
     
     Spotify keeps its last track while the radio plays -- the
     supervisor pauses it, it does not forget it -- so its cover is
     still there to be asked for, and asking would put an album
     behind a station logo. */
  const cover = $derived(onAir ? '' : coverFor(track))

  const dial = $derived(
    radio.state.frequency ?? radio.state.last ?? null,
  )
  const mark = $derived(logoForPi(rds.pi, isDark()))

  /* One set of labels and one set of buttons, whichever source is
     behind them. The tile has room for one thing at a time, and
     two near-identical branches of markup would drift. */
  const title = $derived(
    onAir
      ? rds.ps || nameForPi(rds.pi) || radio.state.name || 'FM radio'
      : track?.title || 'Nothing playing',
  )

  const detail = $derived(
    onAir
      ? rds.radiotext ||
        (dial === null ? 'FM radio' : `${dial.toFixed(1)} MHz`)
      : track?.artist || 'Pick a source',
  )

  const sounding = $derived(
    onAir || track?.status === 'playing',
  )

  const working = $derived(
    onAir ? radio.busy : track ? busyWith(track.source) : false,
  )

  const hasTransport = $derived(onAir || !!track)

  const back = () =>
    onAir ? seekRadio(-1) : track && command(track.source, 'prev')

  const forward = () =>
    onAir ? seekRadio(1) : track && command(track.source, 'next')

  const playPause = () =>
    onAir ? toggleRadio() : track && toggle(track.source)

  /* The map tile: a live map behind it once there is one to show,
     and the plain link it always was when there is not. */
  let mapStatus = $state<CarMapStatus>('loading')
  let carLook = $state<CarLook>({ source: 'none', pointing: false })
  const mapShown = $derived(mapStatus === 'ready')

  /** The same readout as the map screen's corner. */
  const speed = $derived(speedOf(position.reading))

  /** The tile's spoken name: what the screen shows as a map and a
   *  marker, in words. */
  const whereabouts = $derived.by(() => {
    if (mapStatus === 'unavailable') return 'No offline map installed'
    switch (carLook.source) {
      case 'gps':
        return speed !== null && speed >= 1
          ? `Live position, ${speed} km/h`
          : 'Live position'
      case 'last':
        return 'Last known position · waiting for GPS'
      case 'pin':
        return 'Pinned position'
      default:
        return 'Waiting for GPS'
    }
  })
</script>

<div class="dashboard">
  <Card padding="xl" gap="none" direction="row" align="start"
        justify="between">
    <div class="when">
      <div class="eyebrow">{greeting}</div>
      <div class="clock">{clock}</div>
      <div class="date">{date}</div>
    </div>

    <!-- The weather at the top, the address at the foot, level with
         the clock and the date beside them. Only the weather opens the
         forecast: it is the thing you would reach for, and the address
         is something to read. -->
    <div class="side">
      <button
        class="where"
        aria-label="Weather: {temperature}°, {nameFor(condition)}. Open the forecast"
        onclick={() => (forecastOpen = true)}
      >
        <Icon name={iconFor(condition)} size={34} />
        <span class="temp">{temperature}°</span>
      </button>

      <span class="eyebrow place">
        <span>{placeLines[0]}</span>
        {#if placeLines[1]}
          <span>{placeLines[1]}</span>
        {/if}
      </span>
    </div>
  </Card>

  <div class="tiles">
    <!-- Not a link, unlike the tiles beside it: the transport
         buttons are targets of their own, and one inside a link is a
         guess as to which you hit. The text is the link instead. -->
    <!-- No eyebrow over artwork. It was the only thing up there, and
         carrying it meant veiling the whole cover to keep it legible
    <!-- What is making sound, whichever source it is.
         
         The radio takes the tile when it is on air: it is not a
         player the media store can see, so without this the car
         would be playing FM under a tile saying nothing playing. -->
    <Card
      eyebrow={cover || onAir ? '' : 'Now playing'}
      justify="between"
      class={cover ? 'now-playing covered' : 'now-playing'}
    >
      <!-- The cover behind the whole tile rather than beside the
           text. Nothing here when a source has no artwork -- AVRCP
           never sends any -- so the thumb stands in instead. -->
      {#if cover}
        <div class="cover" style:--art="url({cover})" aria-hidden="true">
        </div>
      {/if}

      {#if onAir}
        <!-- The station, in the middle of the tile: its logo where
             there is one, and the frequency where there is not. Not
             a background like a cover -- a wordmark spread behind
             text would be unreadable as both. -->
        <a class="dial" href="/media/fm">
          {#if mark}
            <img class="mark" src={mark} alt={title} />
          {:else if dial !== null}
            <span class="tuned">
              <span class="figure">{dial.toFixed(1)}</span>
              <span class="unit">MHz</span>
            </span>
          {/if}
        </a>
      {/if}

      <div class="foot" class:over-art={!!cover}>
        <a class="labels-link" href={onAir ? '/media/fm' : '/media'}>
          {#if !cover && !onAir}
            <span class="thumb" class:playing={sounding}>
              <Icon name="note" size={26} />
            </span>
          {/if}
          <span class="labels">
            <span class="title">{title}</span>
            <span class="detail">{detail}</span>
          </span>
        </a>

        {#if hasTransport}
          <div class="transport">
            <Button
              square
              label={onAir ? 'Previous station' : 'Previous'}
              disabled={working}
              onclick={back}
            >
              <Icon name="previous" size={24} />
            </Button>

            <Button
              square
              label={sounding ? 'Pause' : 'Play'}
              disabled={working}
              onclick={playPause}
            >
              <Icon name={sounding ? 'pause' : 'play'} size={26} />
            </Button>

            <Button
              square
              label={onAir ? 'Next station' : 'Next'}
              disabled={working}
              onclick={forward}
            >
              <Icon name="next" size={24} />
            </Button>
          </div>
        {/if}
      </div>
    </Card>

    <!-- The map under the whole tile, centred on the car, like the
         cover in the tile beside it. Not interactive: the tile is one
         target, and the map screen is where the map is used. -->
    <Card
      href="/map"
      justify="end"
      class={mapShown ? 'navigation live' : 'navigation'}
    >
      <!-- Speed top right and the licence line bottom right, where
           the map screen has them, so the tile reads as a small copy
           of it. Inside the backdrop: both belong to the map, and
           appear with it. -->
      <div class="backdrop" class:shown={mapShown} aria-hidden="true">
        <CarMap bind:status={mapStatus} bind:look={carLook} />
        <!-- The next turn while a route is being driven, as on the map
             screen, smaller. CarMap keeps the session current. -->
        {#if turnShown() && nav.session}
          <div class="turn">
            <TurnBanner session={nav.session} compact />
          </div>
        {/if}
        <div class="speed">
          <span class="speed-figure">{speed ?? '–'}</span>
          <span class="speed-unit">km/h</span>
        </div>
        <span class="osm">© OpenStreetMap</span>
      </div>

      <!-- Spoken, since the tile has no visible words to be its name.
           Whether the position is live shows on the car itself: the
           marker is grey when it is not. -->
      <div class="foot">
        <span class="thumb accent">
          <Icon name="map" size={26} />
        </span>
        <span class="spoken">Open map. {whereabouts}</span>
      </div>
    </Card>
  </div>
</div>

<WeatherDialog
  open={forecastOpen}
  onclose={() => (forecastOpen = false)}
/>

<style>
  .dashboard {
    display: grid;
    /* minmax(0, ...) so the tiles row can shrink: a bare 1fr floors
       at min-content and would push the page past the screen. */
    grid-template-rows: auto minmax(0, 1fr);
    gap: var(--spacing-l);
    height: 100%;
    padding: var(--spacing-l);
  }

  /* The clock is the one thing read at a glance from the driver's
     seat, so it gets the display face and far more size than
     anything around it. */
  .clock {
    margin: 6px 0 4px;
    font-family: var(--font-display);
    font-size: 60px;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .date {
    font-size: 15px;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  /* The card's full height, so the address can sit at its foot while
     the weather stays at the top. */
  .side {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--spacing);
    align-self: stretch;
  }

  /* Pulled out by its own padding, so the pressed background has room
     around the icon and figure without moving them off the edge. */
  .where {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    padding: var(--spacing-xs) var(--spacing-s);
    margin: calc(var(--spacing-xs) * -1) calc(var(--spacing-s) * -1);
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: var(--radius-sm);
  }

  .where:active {
    background: var(--panel-2);
  }

  .where:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  /* Two lines held close, so they read as one address rather than
     two labels. */
  .place {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 3px;
    line-height: 1.2;
    text-align: right;
  }

  .temp {
    font-family: var(--font-display);
    font-size: 38px;
    font-weight: 600;
    line-height: 1;
    color: var(--text);
  }

  .tiles {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: minmax(0, 1fr);
    gap: var(--spacing-l);
    min-height: 0;
  }

  .foot {
    display: flex;
    align-items: center;
    gap: var(--spacing);
  }

  /* The station, filling the space above the labels.
     
     A link like the labels are, because the whole point of looking
     at it is to go and change it. Padded so a wordmark is not
     touching the card edges -- the cover treatment can bleed to the
     edge because it is a backdrop; this is the content. */
  .dial {
    position: relative;
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    min-height: 0;
    padding: var(--spacing-s) var(--spacing-l) var(--spacing);
    color: inherit;
    text-decoration: none;
  }

  .dial:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: var(--radius-sm);
  }

  /* Half the tile, whichever way round it is.
     
     Positioned rather than laid out in flow: a percentage height
     against a flex item is a question about whether the parent's
     height is definite, and the answer has been wrong before. An
     absolute box with `inset: 0` resolves against the padding box
     of the positioned ancestor, which it always has.
     
     `margin: auto` on all four sides centres it, and `contain`
     keeps the shape inside the box -- so a wide wordmark uses the
     width and a tall badge uses the height. */
  .mark {
    position: absolute;
    inset: 0;
    width: 50%;
    height: 50%;
    margin: auto;
    object-fit: contain;
  }

  .tuned {
    display: flex;
    align-items: baseline;
    gap: var(--spacing-xs);
  }

  .figure {
    font-family: var(--font-display);
    font-size: 52px;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .unit {
    font-size: 16px;
    color: var(--text-dim);
  }

  /* The text and the thumb are the link; the buttons are not.
     
     Card resets text-decoration for the anchor it renders itself,
     which does not reach one written here. */
  .labels-link {
    display: flex;
    align-items: center;
    gap: var(--spacing);
    flex: 1;
    min-width: 0;
    color: inherit;
    text-decoration: none;
    border-radius: var(--radius-sm);
  }

  /* The cover behind the tile.
   *
   * A gradient stacked above the image in the same background, not
   * opacity on the element: opacity fades everything drawn inside it,
   * so a scrim there would be faded too and buy nothing.
   *
   * 35% over most of the picture, going solid only at the bottom
   * edge where the text sits. */
  .cover {
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(
        to top,
        var(--surface) 0%,
        color-mix(in srgb, var(--surface) 35%, transparent) 45%,
        color-mix(in srgb, var(--surface) 35%, transparent) 100%
      ),
      var(--art);
    background-size: cover;
    background-position: center;
  }

  /* :global because the class lands on the Card's own element. */
  .tiles :global(.now-playing) {
    position: relative;
    overflow: hidden;
  }

  /* Only with a cover. There is no eyebrow then, and one child cannot
     be spaced against anything -- the row would sit at the top with
     the picture empty beneath it.
     
     Without a cover the eyebrow is back, and Card's own spacing puts
     it at the top and the row at the bottom, which is right. Applying
     this to both would drag the eyebrow down to meet the row. */
  .tiles :global(.now-playing.covered) {
    justify-content: flex-end;
  }

  /* Above the cover. A positioned element paints over its unpositioned
     siblings whatever the order, so the content has to be positioned
     too -- and the cover excluded, or this rule would win over its own
     `position: absolute` and drop it back into the flow. */
  .tiles :global(.now-playing) > :global(*:not(.cover)) {
    position: relative;
  }

  /* Over a picture rather than a flat colour, so the text carries its
     own backing: a halo in the card colour, which is a hole punched
     around the letters rather than a box drawn behind them.
     
     Both lines full strength. Dimming the artist to separate it from
     the title works against a panel and not against artwork, where it
     simply disappears; the size difference does that job. */
  .over-art .title,
  .over-art .detail {
    color: var(--text);
    opacity: 1;
    text-shadow:
      0 1px 3px var(--surface),
      0 0 10px var(--surface),
      0 0 20px var(--surface);
  }

  /* The map tile: positioned and clipped like the media tile, with
     the content above the map for the same reason. */
  .tiles :global(.navigation) {
    position: relative;
    overflow: hidden;
  }

  /* z-index as well as position: the map is positioned too and comes
     after the eyebrow, so without it the map would paint over it. */
  .tiles :global(.navigation) > :global(*:not(.backdrop)) {
    position: relative;
    z-index: 1;
  }

  /* Faded in once it has drawn, so the tile never shows an empty
     grey box while the map is starting. */
  .backdrop {
    position: absolute;
    inset: 0;
    opacity: 0;
    transition: opacity 0.4s ease;
  }

  .backdrop.shown {
    opacity: 1;
  }

  /* Top left, up to the speed circle: its width and two gaps. */
  .turn {
    position: absolute;
    top: var(--spacing);
    left: var(--spacing);
    right: calc(72px + var(--spacing) * 2);
  }

  /* As on the map screen, a little smaller for the tile. Full
     brightness: it is read at a glance, like the clock. */
  .speed {
    position: absolute;
    top: var(--spacing);
    right: var(--spacing);
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 72px;
    height: 72px;
    justify-content: center;
    border-radius: 50%;
    background: var(--readout);
    /* A light shadow so the circle has an edge where the map under
       it is close to its own colour -- white on a pale Day map. */
    box-shadow: 0 1px 4px rgb(0 0 0 / 0.3);
    line-height: 1;
  }

  .speed-figure {
    font-family: var(--font-display);
    font-size: 30px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }

  .speed-unit {
    margin-top: 2px;
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  /* The tile's name for a screen reader, now that it shows none. */
  .spoken {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  /* Required by the ODbL licence the map data is under. */
  .osm {
    position: absolute;
    right: var(--spacing);
    bottom: var(--spacing-s);
    font-size: 10px;
    color: var(--text-faint);
  }

  .labels-link:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 4px;
  }

  /* Plain rather than quiet: a transparent button over artwork is
     an outline and not much else. These sit on --panel-2, which
     reads as a button whatever is behind the card. */
  .transport {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }

  /* Accented while something is actually coming out, so the tile
     says at a glance whether the car is playing or merely has
     something queued. */
  .thumb.playing {
    color: var(--accent-ink);
    background: var(--accent);
  }

  /* A block rather than a bare icon: the whole tile is the target,
     and it gives the eye something to land on from across the
     cabin. */
  .thumb {
    display: grid;
    place-items: center;
    width: 62px;
    height: 62px;
    color: var(--text-dim);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .thumb.accent {
    color: var(--accent-ink);
    background: var(--accent);
  }

  .labels {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }

  /* Truncated, because the transport buttons sit beside it: a long
     track name would otherwise push them off the card. */
  .title {
    font-size: 22px;
    font-weight: 600;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .detail {
    font-size: 15px;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
</style>
