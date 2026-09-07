<script lang="ts">
  import Icon from '../Icon.svelte'
  import Button from './Button.svelte'
  import Dialog from './Dialog.svelte'
  import Spinner from './Spinner.svelte'
  import { untrack } from 'svelte'
  import {
    choose,
    iconFor,
    load,
    loadPlaces,
    nameFor,
    weather,
  } from '../weather.svelte'
  import { CURRENT_PLACE, type Day } from '../api/types'

  interface Props {
    open: boolean
    onclose: () => void
  }

  let { open, onclose }: Props = $props()

  /* untracked, because loadPlaces reads weather.places to decide
     whether to fetch and then sets it. */
  $effect(() => {
    if (open) untrack(() => loadPlaces())
  })

  /* "Here" first, then whatever has been saved. Reserved rather than
     stored, so it is added rather than expected in the list. */
  const places = $derived([
    { name: CURRENT_PLACE, label: 'Here' },
    ...weather.places.map((place) => ({
      name: place.name,
      /* Capitalised for display only. The name is the key the daemon
         knows it by and is left alone. */
      label: place.name.charAt(0).toUpperCase() + place.name.slice(1),
    })),
  ])

  const forecast = $derived(weather.forecast)
  const now = $derived(forecast?.current)

  /** Enough to scroll, not so many that the strip is a chore. */
  const HOURS = 24

  const hours = $derived(forecast?.hourly.slice(0, HOURS) ?? [])
  const days = $derived(forecast?.daily ?? [])

  const clock = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleTimeString('sv-SE', {
          hour: '2-digit',
          minute: '2-digit',
        })
      : ''

  /* Today by name rather than by date: nobody counts forward from a
     number to work out which day they are looking at. */
  function label(day: Day, index: number): string {
    if (index === 0) return 'Today'
    if (!day.date) return ''
    return new Date(day.date).toLocaleDateString('en-GB', {
      weekday: 'short',
    })
  }

  const round = (value: number | null | undefined) =>
    value === null || value === undefined ? '—' : `${Math.round(value)}`

  /** Wind in km/h, since that is what a car speedometer reads in. */
  const kmh = (metresPerSecond: number | null) =>
    metresPerSecond === null ? '—' : `${Math.round(metresPerSecond * 3.6)}`

  /* Only the readings this provider actually sent. MET has no
     visibility and OpenWeather no percentiles, and a tile reading
     "—" says nothing worth the space it takes. */
  const stats = $derived.by(() => {
    if (!now) return []

    const all = [
      { label: 'Feels like', value: round(now.feels_like), unit: '°' },
      { label: 'Wind', value: kmh(now.wind_speed), unit: ' km/h' },
      { label: 'Humidity', value: round(now.humidity), unit: '%' },
      { label: 'UV index', value: round(now.uv_index), unit: '' },
      { label: 'Cloud', value: round(now.cloud_cover), unit: '%' },
      { label: 'Pressure', value: round(now.pressure), unit: ' hPa' },
      {
        label: 'Visibility',
        value:
          now.visibility === null
            ? '—'
            : `${Math.round(now.visibility / 1000)}`,
        unit: ' km',
      },
      { label: 'Dew point', value: round(now.dew_point), unit: '°' },
    ]

    return all.filter((stat) => stat.value !== '—')
  })
</script>

<Dialog {open} {onclose} title="Weather" width={700}>
  {#snippet children()}
    {#if weather.loading && !forecast}
      <div class="pending">
        <Spinner label="Loading the forecast" />
      </div>
    {:else if !forecast}
      <div class="pending">
        <p class="what">No forecast</p>
        <p class="detail">{weather.error || 'Nothing has arrived yet.'}</p>
      </div>
    {:else}
      {#if places.length > 1}
        <div class="places">
          {#each places as place (place.name)}
            <Button
              variant="quiet"
              pressed={weather.place === place.name}
              disabled={weather.loading}
              onclick={() => choose(place.name)}
            >
              {place.label}
            </Button>
          {/each}

          <!-- Beside the chips rather than over the readings: what is
               being waited for is the place, and that is where the
               eye already is. -->
          {#if weather.loading}
            <span class="switching">
              <Spinner size={20} label="Loading the forecast" />
            </span>
          {/if}
        </div>
      {/if}

      <!-- Dimmed while a new place loads. The numbers below are still
           the last place's, and they have to look provisional or they
           read as the new one's. -->
      <div class="readings" class:stale={weather.loading}>
        <section>
          <div class="eyebrow">Now</div>
          <div class="current">
            <Icon name={iconFor(now?.condition ?? 'unknown')} size={44} />
            <span class="degrees">{round(now?.temperature)}°</span>
            <span class="says">{nameFor(now?.condition ?? 'unknown')}</span>
          </div>
        </section>

        {#if stats.length}
          <section>
            <div class="stats">
              {#each stats as stat (stat.label)}
                <div class="stat">
                  <span class="eyebrow">{stat.label}</span>
                  <span class="reading">{stat.value}{stat.unit}</span>
                </div>
              {/each}
            </div>
          </section>
        {/if}

        {#if hours.length}
          <section>
            <div class="eyebrow">Next hours</div>
            <!-- Scrolls sideways rather than wrapping: a run of hours
                 reads as a line, and wrapping it into a block loses
                 that. -->
            <div class="hours">
              {#each hours as hour (hour.time)}
                <div class="hour">
                  <span class="at">{clock(hour.time)}</span>
                  <Icon name={iconFor(hour.condition)} size={22} />
                  <span class="hour-temp">{round(hour.temperature)}°</span>
                  <span class="chance">
                    {round(hour.precipitation_probability)}%
                  </span>
                </div>
              {/each}
            </div>
          </section>
        {/if}

        {#if days.length}
          <section>
            <div class="eyebrow">Next days</div>
            <div class="days">
              {#each days as day, index (day.date)}
                <div class="day">
                  <span class="day-name">{label(day, index)}</span>
                  <Icon name={iconFor(day.condition)} size={22} />
                  <span class="chance">
                    {day.precipitation > 0
                      ? `${day.precipitation.toFixed(1)} mm`
                      : ''}
                  </span>
                  <span class="low">{round(day.low)}°</span>
                  <span class="high">{round(day.high)}°</span>
                </div>
              {/each}
            </div>
          </section>
        {/if}

        <p class="source">
          {forecast.place} · via {forecast.provider}
          {#if forecast.updated}
            · {clock(forecast.updated)}
          {/if}
        </p>
      </div>
    {/if}
  {/snippet}

  {#snippet footer()}
    <Button
      variant="quiet"
      onclick={() => load(true)}
      disabled={weather.loading}
    >
      <Icon name="refresh" size={18} />
      Refresh
    </Button>
    <Button variant="primary" onclick={onclose}>Close</Button>
  {/snippet}
</Dialog>

<style>
  section {
    margin-bottom: var(--spacing-l);
  }

  /* Scrolls sideways rather than wrapping: however many places get
     saved, the row stays one line and the dialog does not grow a
     block of chips at the top of it. */
  .places {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    margin-bottom: var(--spacing-l);
    padding-bottom: 4px;
    overflow-x: auto;
  }

  .switching {
    display: grid;
    place-items: center;
    flex-shrink: 0;
    padding-left: var(--spacing-xs);
  }

  .readings {
    transition: opacity 160ms ease;
  }

  .readings.stale {
    opacity: 0.4;
    /* Nothing in here should be tappable while it describes somewhere
       else. */
    pointer-events: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .readings {
      transition: none;
    }
  }

  .pending {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--spacing-s);
    padding: var(--spacing-xl) 0;
    text-align: center;
  }

  .what {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
  }

  .detail {
    margin: 0;
    font-size: 13px;
    color: var(--text-dim);
  }

  .current {
    display: flex;
    align-items: center;
    gap: var(--spacing);
    margin-top: var(--spacing-xs);
    color: var(--text-dim);
  }

  .degrees {
    font-family: var(--font-display);
    font-size: 40px;
    font-weight: 600;
    line-height: 1;
    color: var(--text);
  }

  .says {
    font-size: 16px;
    color: var(--text-dim);
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--spacing-s);
  }

  /* Wider dialog, so the strip shows more hours before it has to be
     scrolled. */
  .hour {
    flex: 0 0 78px;
  }

  .stat {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
    padding: var(--spacing-s) var(--spacing);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .reading {
    font-size: 18px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .hours {
    display: flex;
    gap: 8px;
    margin-top: var(--spacing-xs);
    padding-bottom: 4px;
    overflow-x: auto;
  }

  .hour {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: var(--spacing-s) 0;
    color: var(--text-dim);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .at {
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .hour-temp {
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
  }

  .chance {
    font-size: 12px;
    color: var(--blue);
    font-variant-numeric: tabular-nums;
  }

  .days {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: var(--spacing-xs);
  }

  .day {
    display: grid;
    grid-template-columns: 68px auto 1fr auto auto;
    align-items: center;
    gap: var(--spacing-s);
    min-height: 50px;
    padding: 0 var(--spacing);
    color: var(--text-dim);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .day-name {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
  }

  /* The low dimmed and the high in full: read together they are a
     range, and the eye should land on the number that decides what
     you wear. */
  .low {
    font-variant-numeric: tabular-nums;
  }

  .high {
    min-width: 34px;
    font-size: 16px;
    font-weight: 600;
    text-align: right;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }

  .source {
    margin: 0;
    padding-bottom: var(--spacing-s);
    font-size: 12px;
    color: var(--text-faint);
  }
</style>
