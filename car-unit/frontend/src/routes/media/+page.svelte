<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Segmented from '$lib/ui/Segmented.svelte'

  /* Placeholder throughout. Nothing is wired to the daemon. */

  type Source = 'bluetooth' | 'fm' | 'usb'

  let source = $state<Source>('bluetooth')
  let playing = $state(true)
  let position = $state(299)

  const track = {
    title: 'Redbone',
    artist: 'Childish Gambino',
    album: 'Awaken, My Love!',
    via: 'Fake Phone',
    length: 327,
  }

  const queue = [
    { title: 'Harbour Lights — Ora Vale', length: '3:52' },
    { title: 'Northbound — Kite Season', length: '4:18' },
    { title: 'Slow Ferry — Halva Vägen', length: '2:59' },
  ]

  const clock = (seconds: number) => {
    const whole = Math.max(0, Math.round(seconds))
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
  }

  const elapsed = $derived((position / track.length) * 100)
</script>

<div class="media">
  <Segmented
    label="Source"
    options={[
      { value: 'bluetooth', label: 'Bluetooth' },
      { value: 'fm', label: 'FM' },
      { value: 'usb', label: 'USB' },
    ]}
    value={source}
    onchange={(v: Source) => (source = v)}
  />

  <!-- A gradient stands in for artwork. Bluetooth rarely sends any,
       and an empty grey square reads as broken. -->
  <div class="art">
    <Icon name="note" size={56} />
  </div>

  <div class="titles">
    <h2>{track.title}</h2>
    <p class="artist">{track.artist}</p>
    <p class="album">{track.album}</p>
    <p class="via">via {track.via}</p>
  </div>

  <div class="progress">
    <span class="time">{clock(position)}</span>
    <input
      type="range"
      min="0"
      max={track.length}
      value={position}
      style:--fill="{elapsed}%"
      aria-label="Position"
      oninput={(e) => (position = +e.currentTarget.value)}
    />
    <span class="time">{clock(track.length)}</span>
  </div>

  <div class="transport">
    <button class="round" aria-label="Previous">
      <Icon name="previous" size={22} />
    </button>

    <button
      class="round primary"
      aria-label={playing ? 'Pause' : 'Play'}
      onclick={() => (playing = !playing)}
    >
      <Icon name={playing ? 'pause' : 'play'} size={30} />
    </button>

    <button class="round" aria-label="Next">
      <Icon name="next" size={22} />
    </button>
  </div>

  <section class="queue">
    <div class="eyebrow">Up next</div>
    {#each queue as item (item.title)}
      <div class="queued">
        <span>{item.title}</span>
        <span class="time">{item.length}</span>
      </div>
    {/each}
  </section>
</div>

<style>
  .media {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 18px;
    height: 100%;
    padding: 20px 24px 24px;
    overflow-y: auto;
  }

  .art {
    display: grid;
    place-items: center;
    width: 180px;
    height: 180px;
    color: #fff;
    background: linear-gradient(150deg, #e0b45a, #b06fd0);
    border-radius: var(--radius);
  }

  .titles {
    text-align: center;
  }

  h2 {
    margin: 0;
    font-size: 26px;
    font-weight: 600;
  }

  .artist {
    margin: 4px 0 0;
    font-size: 17px;
    color: var(--text-dim);
  }

  .album,
  .via {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--text-faint);
    opacity: var(--dim-secondary);
  }

  .progress {
    display: flex;
    align-items: center;
    gap: 14px;
    width: 100%;
    max-width: 540px;
    color: var(--text-dim);
  }

  .time {
    min-width: 38px;
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  input[type='range'] {
    flex: 1;
    height: 8px;
    appearance: none;
    border-radius: 4px;
    background: linear-gradient(
      to right,
      var(--accent) var(--fill),
      var(--border) var(--fill)
    );
  }

  input[type='range']::-webkit-slider-thumb {
    appearance: none;
    width: 20px;
    height: 20px;
    background: var(--knob);
    border-radius: 50%;
  }

  input[type='range']::-moz-range-thumb {
    width: 20px;
    height: 20px;
    background: var(--knob);
    border: 0;
    border-radius: 50%;
  }

  input[type='range']:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 6px;
  }

  .transport {
    display: flex;
    align-items: center;
    gap: 22px;
  }

  .round {
    display: grid;
    place-items: center;
    width: 68px;
    height: 68px;
    color: var(--text);
    background: var(--panel-2);
    border: 0;
    border-radius: 50%;
  }

  /* Play is the control reached for without looking, so it is bigger
     and the only one carrying the accent. */
  .round.primary {
    width: 92px;
    height: 92px;
    color: var(--accent-ink);
    background: var(--accent);
  }

  .round:active {
    filter: brightness(0.92);
  }

  .round:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }

  .queue {
    width: 100%;
    max-width: 560px;
    padding: 16px 20px 6px;
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .queued {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
    padding: var(--spacing-s) 0;
    font-size: 15px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--hairline);
  }

  .queued:last-child {
    border-bottom: 0;
  }
</style>
