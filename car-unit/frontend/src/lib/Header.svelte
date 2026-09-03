<script lang="ts">
  import Icon from './Icon.svelte'
  import { status } from './status.svelte'

  interface Props {
    title: string
    volume: number
    onvolume: (value: number) => void
    muted: boolean
    onmute: (muted: boolean) => void
  }

  let { title, volume, onvolume, muted, onmute }: Props = $props()

  /* Temperature, signal and Bluetooth come from the status store --
     placeholders until the daemon feeds them. The clock is local and
     real. */
  let now = $state(new Date())
  const outside = $derived(status.outside)
  const bars = $derived(status.bars)

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

  /* Muting drops the slider to zero and unmuting puts it back: the
     level is kept in `volume` throughout, so the thumb returns to
     where it was rather than to silence.

     Any deliberate move un-mutes. Reaching for the volume is a clear
     enough signal that you want to hear something, and changing a
     level that stays silent is the sort of thing you press twice
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
      value={muted ? 0 : volume}
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

    <a
      class="bluetooth"
      class:connected={status.bluetooth}
      href="/settings/connectivity"
      aria-label={status.bluetooth
        ? 'Bluetooth connected'
        : 'Bluetooth, nothing connected'}
    >
      <Icon
        name={status.bluetooth ? 'bluetooth-connected' : 'bluetooth'}
        size={22}
      />
    </a>

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

  /* No group opacity here. Under Night Panel --dim-secondary drops
     to 0.12, which would fade the controls to nothing however white
     they are set -- and volume is adjusted in the dark more than
     anywhere else. The status block beside it still dims. */
  .volume {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    color: var(--text-dim);
  }

  .round {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    /* Full strength, like the speaker and the readout beside them:
       these are controls, and the row's dim is for labels. */
    color: var(--text);
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

  /* Matches the temperature and clock: same face, same size, same
     strength. All three are glanced at rather than read. */
  .value {
    min-width: 30px;
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }

  .value.muted {
    color: var(--text-faint);
    text-decoration: line-through;
  }

  /* No gap here. Each item pads itself instead, because a uniform
     gap measures box edges and the eye measures ink: the Bluetooth
     glyph sits inside a touch target with whitespace already in it,
     so an even gap left it looking adrift from the temperature.
     Padding per item lets the icon take less and the bare text take
     more, and the row reads evenly. */
  .status {
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  /* Same face and colour as the clock: both are glanced at from the
     driver's seat, and the old dimmed 14px disappeared next to it. */
  /* A link rather than a readout: the whole point is that it takes
     you to the pairing screen, and that is not discoverable if it
     looks like the signal bars beside it. */
  .bluetooth {
    display: grid;
    place-items: center;
    /* Less than its neighbours on purpose. The glyph does not reach
       the edges of its own 24px box -- roughly 3px of air each side --
       so matching their 10px would read as 13. */
    padding: 9px 7px;
    color: var(--text-dim);
    border-radius: var(--radius-sm);
  }

  .bluetooth.connected {
    color: var(--accent);
  }

  .bluetooth:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .temp {
    padding: 0 10px;
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
    padding: 0 10px;
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
    /* Nothing on the right: the header's own padding is the margin
       to the screen edge, and doubling it would push the clock in
       from where the title sits opposite. */
    padding-left: 10px;
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
  }
</style>
