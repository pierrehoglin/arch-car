<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Button from '$lib/ui/Button.svelte'
  import WeatherDialog from '$lib/ui/WeatherDialog.svelte'
  import { iconFor, nameFor, watch, weather } from '$lib/weather.svelte'
  import { coverFor } from '$lib/covers'
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

  const forecast = $derived(weather.forecast)
  const current = $derived(forecast?.current)
  const condition = $derived(current?.condition ?? 'unknown')

  /* Watched here rather than in the root layout: the clock it starts
     is only worth running while something is showing elapsed time,
     and nothing on this screen does. */
  $effect(() => watchMedia())

  const track = $derived(nowPlaying())

  /* Ours for Bluetooth, which never sends any. Everything that shows
     artwork goes through this, so the two screens cannot end up
     disagreeing about when there is a picture. */
  const cover = $derived(coverFor(track))
</script>

<div class="dashboard">
  <Card padding="xl" gap="none" direction="row" align="start"
        justify="between">
    <div class="when">
      <div class="eyebrow">{greeting}</div>
      <div class="clock">{clock}</div>
      <div class="date">{date}</div>
    </div>

    <!-- The whole block opens the forecast, rather than a separate
         control: it is already the thing you would reach for. -->
    <button class="where" onclick={() => (forecastOpen = true)}>
      <span class="eyebrow">{forecast?.place ?? ''}</span>
      <span class="weather">
        <Icon name={iconFor(condition)} size={34} />
        <span class="temp">
          {current?.temperature === null ||
          current?.temperature === undefined
            ? '—'
            : Math.round(current.temperature)}°
        </span>
      </span>
      <span class="eyebrow">{nameFor(condition)}</span>
    </button>
  </Card>

  <div class="tiles">
    <!-- Not a link, unlike the tiles beside it: the transport
         buttons are targets of their own, and one inside a link is a
         guess as to which you hit. The text is the link instead. -->
    <!-- No eyebrow over artwork. It was the only thing up there, and
         carrying it meant veiling the whole cover to keep it legible
         -- for a label a track title and transport buttons already
         make obvious. -->
    <Card
      eyebrow={cover ? '' : 'Now playing'}
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

      <div class="foot" class:over-art={!!cover}>
        <a class="labels-link" href="/media">
          {#if !cover}
            <span class="thumb" class:playing={track?.status === 'playing'}>
              <Icon name="note" size={26} />
            </span>
          {/if}
          <span class="labels">
            <span class="title">{track?.title || 'Nothing playing'}</span>
            <span class="detail">
              {track?.artist || 'Pick a source'}
            </span>
          </span>
        </a>

        {#if track}
          {@const busy = busyWith(track.source)}
          <div class="transport">
            <Button
              square
              label="Previous"
              disabled={busy}
              onclick={() => command(track.source, 'prev')}
            >
              <Icon name="previous" size={24} />
            </Button>

            <Button
              square
              label={track.status === 'playing' ? 'Pause' : 'Play'}
              disabled={busy}
              onclick={() => toggle(track.source)}
            >
              <Icon
                name={track.status === 'playing' ? 'pause' : 'play'}
                size={26}
              />
            </Button>

            <Button
              square
              label="Next"
              disabled={busy}
              onclick={() => command(track.source, 'next')}
            >
              <Icon name="next" size={24} />
            </Button>
          </div>
        {/if}
      </div>
    </Card>

    <Card href="/map" eyebrow="Navigation" justify="between">
      <div class="foot">
        <span class="thumb accent">
          <Icon name="map" size={26} />
        </span>
        <span class="labels">
          <span class="title">Open map</span>
          <span class="detail">Offline vector map · live position</span>
        </span>
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

  .where {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
    padding: var(--spacing-xs) var(--spacing-s);
    margin: calc(var(--spacing-xs) * -1) calc(var(--spacing-s) * -1);
    text-align: right;
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

  .weather {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    color: var(--text-dim);
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
