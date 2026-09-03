<script lang="ts">
  import Icon from './Icon.svelte'

  interface Props {
    title: string
    volume: number
    onvolume: (value: number) => void
    muted: boolean
    onmute: (muted: boolean) => void
  }

  let { title, volume, onvolume, muted, onmute }: Props = $props()

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

  /* Any deliberate move of the volume un-mutes. Reaching for it is a
     clear enough signal that you want to hear something, and changing
     a level that stays silent is the sort of thing you press twice
     before noticing. */
  const change = (value: number) => {
    if (muted) onmute(false)
    onvolume(Math.max(0, Math.min(100, value)))
  }

  const step = (delta: number) => change(volume + delta)
</script>

<header class="bar">
  <h1>{title}</h1>

  <div class="volume">
    <button
      class="mute"
      class:muted
      onclick={() => onmute(!muted)}
      aria-pressed={muted}
      aria-label={muted ? 'Unmute' : 'Mute'}
    >
      <Icon name={muted ? 'muted' : 'volume'} size={26} />
    </button>

    <button class="round" onclick={() => step(-5)} aria-label="Quieter">
      <Icon name="remove" size={18} />
    </button>

    <input
      class="slider"
      type="range"
      min="0"
      max="100"
      value={volume}
      style:--fill="{muted ? 0 : volume}%"
      oninput={(e) => change(+e.currentTarget.value)}
      aria-label="Volume"
    />

    <button class="round" onclick={() => step(5)} aria-label="Louder">
      <Icon name="add" size={18} />
    </button>

    <span class="value" class:muted>{volume}</span>
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
    gap: var(--spacing-s);
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  .round {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    color: var(--text-dim);
    background: none;
    /* Just an edge, the same one that divides everything else. A
       filled chip here competed with the slider beside it, which is
       the thing worth looking at. */
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  .round:active {
    background: var(--accent-soft);
  }

  .round:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .slider {
    width: 200px;
    height: 8px;
    appearance: none;
    border-radius: 4px;
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
    width: 18px;
    height: 18px;
    background: var(--knob);
    border-radius: 50%;
  }

  .slider::-moz-range-thumb {
    width: 18px;
    height: 18px;
    background: var(--knob);
    border: 0;
    border-radius: 50%;
  }

  /* Full strength rather than inheriting the row's dim: this is a
     control, not a label, and it is the one thing here pressed
     without looking. */
  .mute {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    color: var(--text);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .mute.muted {
    color: var(--danger);
  }

  .mute:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .value {
    min-width: 24px;
    font-variant-numeric: tabular-nums;
    font-size: 14px;
  }

  .value.muted {
    color: var(--text-faint);
    text-decoration: line-through;
  }

  .status {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--spacing);
  }

  /* Same face and colour as the clock: both are glanced at from the
     driver's seat, and the old dimmed 14px disappeared next to it. */
  .temp {
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text);
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
