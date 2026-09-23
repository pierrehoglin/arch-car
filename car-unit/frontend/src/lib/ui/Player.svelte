<script lang="ts">
  import Icon from '../Icon.svelte'

  export interface Queued {
    title: string
    length: string
  }

  interface Props {
    title: string
    artist?: string
    album?: string
    /** Where it is coming from -- a phone's name, an account. */
    via?: string
    /** Track length in seconds. */
    length: number
    position?: number
    playing?: boolean
    /** Cover art, where the source publishes any. MPRIS does;
     *  AVRCP does not -- the profile can carry it, but BlueZ does
     *  not expose it. */
    art?: string
    /** Two colours standing in for artwork when there is none, so
     *  each source is recognisable at a glance without a logo.
     *  Omitted for a source that never has any -- a coloured square
     *  where a cover would be is a placeholder for something that is
     *  never coming. */
    tint?: [string, string]
    /** Often empty: a queue needs AVRCP browsing over Bluetooth,
     *  which Android supports and iOS does not. */
    queue?: Queued[]

    onplay?: (playing: boolean) => void
    onseek?: (seconds: number) => void
    onprevious?: () => void
    onnext?: () => void
  }

  let {
    title,
    artist = '',
    album = '',
    via = '',
    length,
    position = 0,
    playing = false,
    art = '',
    tint,
    queue = [],
    onplay,
    onseek,
    onprevious,
    onnext,
  }: Props = $props()

  const clock = (seconds: number) => {
    const whole = Math.max(0, Math.round(seconds))
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
  }

  const elapsed = $derived(length > 0 ? (position / length) * 100 : 0)
</script>

<!-- The cover, a stand-in, or nothing at all.
     
     Nothing when a source has neither: AVRCP does not carry artwork
     -- the profile can, but BlueZ does not expose it -- so a square
     of colour there would be waiting for a picture that never
     arrives. Better to let the track sit on its own.

     The image is allowed to fail quietly: it comes from the
     provider's CDN, and a car without signal is the normal case, not
     an error worth showing. -->
{#if art}
  <div class="art">
    <img src={art} alt="" onerror={(e) => (e.currentTarget.hidden = true)} />
  </div>
{:else if tint}
  <div class="art" style:--from={tint[0]} style:--to={tint[1]}></div>
{/if}

<div class="titles">
  <h2>{title}</h2>
  {#if artist}<p class="artist">{artist}</p>{/if}
  {#if album}<p class="album">{album}</p>{/if}
  {#if via}<p class="via">via {via}</p>{/if}
</div>

<div class="progress">
  <span class="time">{clock(position)}</span>
  <input
    type="range"
    min="0"
    max={length}
    value={position}
    style:--fill="{elapsed}%"
    aria-label="Position"
    oninput={(e) => onseek?.(+e.currentTarget.value)}
  />
  <span class="time">{clock(length)}</span>
</div>

<div class="transport">
  <button class="round" aria-label="Previous" onclick={onprevious}>
    <Icon name="previous" size={22} />
  </button>

  <button
    class="round primary"
    aria-label={playing ? 'Pause' : 'Play'}
    onclick={() => onplay?.(!playing)}
  >
    <Icon name={playing ? 'pause' : 'play'} size={30} />
  </button>

  <button class="round" aria-label="Next" onclick={onnext}>
    <Icon name="next" size={22} />
  </button>
</div>

<!-- Hidden rather than empty: a source that cannot report a queue
     would otherwise show a box that never fills. -->
{#if queue.length}
  <section class="queue">
    <div class="eyebrow">Up next</div>
    {#each queue as item (item.title)}
      <div class="queued">
        <span>{item.title}</span>
        <span class="time">{item.length}</span>
      </div>
    {/each}
  </section>
{/if}

<style>
  .art img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: inherit;
  }

  .art {
    display: grid;
    place-items: center;
    width: 180px;
    height: 180px;
    color: #fff;
    background: linear-gradient(150deg, var(--from), var(--to));
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
    padding: var(--spacing) var(--spacing-l) 6px;
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
