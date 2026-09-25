<script lang="ts">
  import Icon from './Icon.svelte'
  import { status } from './status.svelte'
  import { bluetooth, connected } from './bluetooth.svelte'
  import { mode, network, online } from './network.svelte'

  interface Props {
    title: string
    volume: number
    /** An absolute level, from the slider. */
    onvolume: (value: number) => void
    /** A step, from the buttons. Sent as a step rather than a level
     *  so the daemon reads and sets in one call -- nothing can
     *  change in between. */
    onstep: (delta: number) => void
    muted: boolean
    onmute: (muted: boolean) => void
  }

  let { title, volume, onvolume, onstep, muted, onmute }: Props = $props()

  /* Temperature, signal and Bluetooth come from the status store --
     placeholders until the daemon feeds them. The clock is local and
     real. */
  let now = $state(new Date())
  const outside = $derived(status.outside)
  const bars = $derived(status.bars)

  /* What the badge has to say.
   *
   * Off is not the same as nothing connected. With the service
   * stopped there is no radio to connect anything to, so the badge
   * goes rather than sitting there implying the car is looking.
   *
   * The root layout follows Bluetooth for the whole session, so this
   * is already current wherever you are. */
  const radio = $derived(bluetooth.state.adapter.service_active)
  const phone = $derived(connected())

  /* The radio's own badge. Hotspot and Wi-Fi are different enough to
     be worth different marks: one means the car is on a network, the
     other that it is serving one. */
  const net = $derived(mode())
  const netIcon = $derived(net === 'hotspot' ? 'router' : 'wifi')
  const netLabel = $derived(
    net === 'hotspot'
      ? `Hotspot${network.state.hotspot.ssid
          ? `, ${network.state.hotspot.ssid}`
          : ''}`
      : network.state.wifi.connected
        ? `Wi-Fi, ${network.state.wifi.ssid}`
        : 'Wi-Fi, not connected',
  )

  /* The speaker shows roughly how loud it is, so the icon means
     something at a glance rather than only saying "audio". Muted
     wins over the level: the level is still whatever it was, and
     showing it would suggest sound is coming out. */
  const speaker = $derived(
    muted
      ? 'muted'
      : volume === 0
        ? 'volume-zero'
        : volume <= 33
          ? 'volume-low'
          : volume <= 66
            ? 'volume-mid'
            : 'volume',
  )

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
     level is held by the store throughout, so the thumb returns to
     where it was rather than to silence.

     Un-muting on a move is the store's job, since the slider and the
     buttons both want it and it is one rule. */
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
      <Icon name={speaker} size={26} />
    </button>

    <button class="round" onclick={() => onstep(-5)} aria-label="Quieter">
      <Icon name="remove" size={18} />
    </button>

    <input
      class="slider"
      type="range"
      min="0"
      max="100"
      value={muted ? 0 : volume}
      style:--fill="{muted ? 0 : volume}%"
      oninput={(e) => onvolume(+e.currentTarget.value)}
      aria-label="Volume"
    />

    <button class="round" onclick={() => onstep(5)} aria-label="Louder">
      <Icon name="add" size={18} />
    </button>

    <span class="value" class:muted>{volume}</span>
  </div>

  <div class="status">
    {#if outside !== null}
      <span class="temp">{outside}°</span>
    {/if}

    <a
      class="net"
      class:idle={!online()}
      href="/settings/connectivity"
      aria-label={netLabel}
    >
      <Icon name={netIcon} size={22} />
    </a>

    {#if radio}
      <a
        class="bluetooth"
        href="/settings/connectivity"
        aria-label={phone
          ? `Bluetooth, ${phone.name} connected`
          : 'Bluetooth, nothing connected'}
      >
        <Icon
          name={phone ? 'bluetooth-connected' : 'bluetooth'}
          size={22}
        />
      </a>
    {/if}

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
    /* The title and status columns may shrink; the volume group in
       the middle keeps its natural width. */
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
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
  /* Dimmed when the car is neither on a network nor serving one --
     it is still a thing you can go and change, so it stays rather
     than disappearing the way the Bluetooth badge does when its
     service is stopped. */
  .net {
    display: grid;
    place-items: center;
    padding: 9px 7px;
    color: var(--text);
    border-radius: var(--radius-sm);
  }

  .net.idle {
    color: var(--text-dim);
  }

  .net:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .bluetooth {
    display: grid;
    place-items: center;
    /* Less than its neighbours on purpose. The glyph does not reach
       the edges of its own 24px box -- roughly 3px of air each side --
       so matching their 10px would read as 13. */
    padding: 9px 7px;
    /* One colour either way. The icon itself changes when something
       is connected, and colouring it as well would say the same
       thing twice -- while spending the accent, which the status bar
       otherwise reserves for the thing being acted on. */
    color: var(--text);
    border-radius: var(--radius-sm);
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
