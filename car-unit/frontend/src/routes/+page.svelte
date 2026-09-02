<script lang="ts">
  import Icon from '$lib/Icon.svelte'

  /* Everything here is placeholder. Nothing is wired to the daemon. */

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

  const place = 'Stockholms kommun'
  const temperature = 21
  const conditions = 'Broken clouds'

  const track = { title: 'Redbone', artist: 'Childish Gambino' }
</script>

<div class="dashboard">
  <section class="card summary">
    <div class="when">
      <div class="eyebrow">{greeting}</div>
      <div class="clock">{clock}</div>
      <div class="date">{date}</div>
    </div>

    <div class="where">
      <div class="eyebrow">{place}</div>
      <div class="weather">
        <Icon name="cloud" size={34} />
        <span class="temp">{temperature}°</span>
      </div>
      <div class="eyebrow">{conditions}</div>
    </div>
  </section>

  <div class="tiles">
    <a class="card tile" href="/media">
      <div class="eyebrow">Now playing</div>
      <div class="foot">
        <span class="thumb">
          <Icon name="note" size={26} />
        </span>
        <span class="labels">
          <span class="title">{track.title}</span>
          <span class="detail">{track.artist}</span>
        </span>
      </div>
    </a>

    <a class="card tile" href="/map">
      <div class="eyebrow">Navigation</div>
      <div class="foot">
        <span class="thumb accent">
          <Icon name="map" size={26} />
        </span>
        <span class="labels">
          <span class="title">Open map</span>
          <span class="detail">Offline vector map · live position</span>
        </span>
      </div>
    </a>
  </div>
</div>

<style>
  .dashboard {
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 24px;
    height: 100%;
    padding: 24px;
  }

  .card {
    background: var(--surface);
    border-radius: var(--radius);
  }

  .summary {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 26px 30px 28px;
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
  }

  .weather {
    display: flex;
    align-items: center;
    gap: 12px;
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
    gap: 24px;
    min-height: 0;
  }

  .tile {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 22px;
    color: inherit;
    text-decoration: none;
  }

  .tile:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .foot {
    display: flex;
    align-items: center;
    gap: 16px;
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
