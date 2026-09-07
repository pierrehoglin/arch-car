<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Card from '$lib/ui/Card.svelte'
  import WeatherDialog from '$lib/ui/WeatherDialog.svelte'
  import { iconFor, nameFor, watch, weather } from '$lib/weather.svelte'

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

  const track = { title: 'Redbone', artist: 'Childish Gambino' }
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
    <Card href="/media" eyebrow="Now playing" justify="between">
      <div class="foot">
        <span class="thumb">
          <Icon name="note" size={26} />
        </span>
        <span class="labels">
          <span class="title">{track.title}</span>
          <span class="detail">{track.artist}</span>
        </span>
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

  .title {
    font-size: 19px;
    font-weight: 600;
  }

  .detail {
    font-size: 13px;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }
</style>
