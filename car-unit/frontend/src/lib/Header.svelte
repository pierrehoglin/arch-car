<script lang="ts">
  import Icon from './Icon.svelte'

  interface Props {
    title: string
    volume: number
    onvolume: (value: number) => void
  }

  let { title, volume, onvolume }: Props = $props()

  /* Temperature and signal are placeholders -- nothing is wired to
     the daemon yet. The clock is local and real. */
  let now = $state(new Date())
  const outside = 19
  const bars = 4

  $effect(() => {
    const timer = setInterval(() => (now = new Date()), 10_000)
    return () => clearInterval(timer)
  })

  const clock = $derived(
    now.toLocaleTimeString('sv-SE', {
      hour: '2-digit',
      minute: '2-digit',
    }),
  )

  const step = (delta: number) =>
    onvolume(Math.max(0, Math.min(100, volume + delta)))
</script>

<header class="bar">
  <h1>{title}</h1>

  <div class="volume">
    <Icon name="volume" size={20} />

    <button class="round" onclick={() => step(-5)} aria-label="Quieter">
      &minus;
    </button>

    <input
      class="slider"
      type="range"
      min="0"
      max="100"
      value={volume}
      style:--fill="{volume}%"
      oninput={(e) => onvolume(+e.currentTarget.value)}
      aria-label="Volume"
    />

    <button class="round" onclick={() => step(5)} aria-label="Louder">
      &plus;
    </button>

    <span class="value">{volume}</span>
  </div>

  <div class="status">
    <span class="temp">{outside}°</span>

    <!-- Drawn rather than an icon, so the number of lit bars is data. -->
    <span class="signal" aria-label="{bars} of 4 bars">
      {#each [1, 2, 3, 4] as level (level)}
        <i class:lit={level <= bars} style:height="{4 + level * 3}px"></i>
      {/each}
    </span>

    <span class="clock">{clock}</span>
  </div>
</header>

<style>
  .bar {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    height: 64px;
    padding: 0 24px;
    background: var(--bar);
    border-bottom: 1px solid var(--hairline);
  }

  h1 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 19px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .volume {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  .round {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    font-size: 17px;
    line-height: 1;
    background: var(--chip);
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  .round:active {
    background: var(--panel-2);
  }

  .slider {
    width: 152px;
    height: 4px;
    appearance: none;
    border-radius: 2px;
    /* Filled to the knob rather than a plain track: the level is the
       information, and a uniform track hides it. */
    background: linear-gradient(
      to right,
      var(--accent) var(--fill),
      var(--border) var(--fill)
    );
  }

  .slider::-webkit-slider-thumb {
    appearance: none;
    width: 16px;
    height: 16px;
    background: var(--knob);
    border-radius: 50%;
  }

  .slider::-moz-range-thumb {
    width: 16px;
    height: 16px;
    background: var(--knob);
    border: 0;
    border-radius: 50%;
  }

  .value {
    min-width: 24px;
    font-variant-numeric: tabular-nums;
    font-size: 14px;
  }

  .status {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 16px;
  }

  .temp {
    font-size: 14px;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  .signal {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 16px;
    opacity: var(--dim-secondary);
  }

  .signal i {
    width: 3px;
    border-radius: 1px;
    background: var(--text-faint);
  }

  .signal i.lit {
    background: var(--text);
  }

  .clock {
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
  }
</style>
