<script lang="ts">
  import Icon from '../Icon.svelte'
  import Avatar from './Avatar.svelte'
  import Spinner from './Spinner.svelte'
  import { photoUrl, type Call } from '../api/call'
  import {
    answer,
    call,
    calls,
    decline,
    duration,
    hangup,
    holdAnswer,
    main,
    minimize,
    phoneOf,
    tone,
    toggleMute,
  } from '../call.svelte'

  /* The call, on whatever screen is showing: top centre, just under
     the status bar, dropping from the indicator it minimizes into.
     Over the screen rather than replacing it -- nothing behind it is
     dimmed or blocked.

     Leads with the call that wants something done first -- a ringing
     one, a waiting second call -- with any other below as a slim row:
     the call already going while a second waits, the one on hold. */

  const lead = $derived(main())
  const others = $derived(lead ? calls().filter((c) => c.id !== lead.id) : [])
  const twoPhones = $derived(call.status.phones.length > 1)

  const STATE: Record<Call['state'], string> = {
    incoming: 'Incoming call',
    waiting: 'Call waiting',
    dialing: 'Calling…',
    alerting: 'Ringing…',
    active: '',
    held: 'On hold',
    ended: 'Call ended',
  }

  const stateLine = (c: Call) =>
    c.state === 'active' ? duration(c) : STATE[c.state]

  const who = (c: Call) => c.name || c.number || 'Unknown number'

  /** The second line: the number when a name is shown, and which
   *  phone when there are two. */
  const detail = (c: Call) =>
    [c.name ? c.number : '', twoPhones ? phoneOf(c)?.name : '']
      .filter(Boolean)
      .join(' · ')

  const muted = $derived(lead ? (phoneOf(lead)?.muted ?? false) : false)

  /* The keypad, for phone menus: open while a call is connected, and
     put away when the call it was for is not the one leading. */
  let keypad = $state(false)
  let typed = $state('')
  let keypadFor = ''
  $effect(() => {
    const id = lead?.id ?? ''
    if (id !== keypadFor) {
      keypadFor = id
      keypad = false
      typed = ''
    }
  })

  const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#']

  function press(digit: string): void {
    if (!lead) return
    typed = (typed + digit).slice(-16)
    tone(lead, digit)
  }

  /* A photo that fails to load -- a book synced on another unit, a
     cache cleared -- falls back to initials. */
  let broken = $state('')
</script>

{#if call.open && lead}
  <section
    class="card"
    class:ringing={lead.state === 'incoming' || lead.state === 'waiting'}
    class:ended={lead.state === 'ended'}
    aria-label="Call"
    aria-live="polite"
  >
    <header>
      {#if lead.photo && broken !== lead.photo}
        <img
          class="photo"
          src={photoUrl(lead.photo)}
          alt=""
          onerror={() => (broken = lead?.photo ?? '')}
        />
      {:else}
        <Avatar name={who(lead)} size={64} />
      {/if}

      <div class="who">
        <span class="name">{who(lead)}</span>
        {#if detail(lead)}
          <span class="detail">{detail(lead)}</span>
        {/if}
        <span class="state" class:live={lead.state === 'active'}>
          {stateLine(lead)}
        </span>
      </div>

      <button class="minimize" aria-label="Minimize" onclick={minimize}>
        <Icon name="chevron-up" size={24} />
      </button>
    </header>

    {#if others.length}
      <ul class="others">
        {#each others as other (other.id)}
          <li>
            <Avatar name={who(other)} size={32} />
            <span class="other-name">{who(other)}</span>
            <span class="other-state">
              {other.state === 'active' ? `On call · ${duration(other)}` : stateLine(other)}
            </span>
          </li>
        {/each}
      </ul>
    {/if}

    {#if keypad && lead.state === 'active'}
      <div class="keypad">
        <div class="typed" class:empty={!typed}>{typed || 'Tones for menus'}</div>
        <div class="keys">
          {#each KEYS as key (key)}
            <button class="key" onclick={() => press(key)}>{key}</button>
          {/each}
        </div>
      </div>
    {/if}

    {#if call.error}
      <p class="error" role="alert">{call.error}</p>
    {/if}

    <div class="actions">
      {#if lead.state === 'incoming' || lead.state === 'waiting'}
        <button
          class="action end"
          aria-label="Decline"
          disabled={!!call.busy}
          onclick={() => decline(lead)}
        >
          <span class="round">
            {#if call.busy === 'decline'}
              <Spinner size={22} label="Declining" />
            {:else}
              <Icon name="phone-off" size={28} />
            {/if}
          </span>
        </button>
        <button
          class="action answer"
          aria-label={lead.state === 'waiting' ? 'Answer and hold' : 'Answer'}
          disabled={!!call.busy}
          onclick={() => (lead.state === 'waiting' ? holdAnswer(lead) : answer(lead))}
        >
          <span class="round">
            {#if call.busy === 'answer' || call.busy === 'hold'}
              <Spinner size={22} label="Answering" />
            {:else}
              <Icon name="phone" size={28} />
            {/if}
          </span>
        </button>
      {:else if lead.state === 'active'}
        <button
          class="action toggle"
          class:on={muted}
          aria-label="Mute"
          aria-pressed={muted}
          disabled={!!call.busy}
          onclick={() => toggleMute(lead)}
        >
          <span class="round">
            {#if call.busy === 'mute'}
              <Spinner size={22} label="Muting" />
            {:else}
              <Icon name={muted ? 'mic-off' : 'mic'} size={26} />
            {/if}
          </span>
        </button>
        <button
          class="action toggle"
          class:on={keypad}
          aria-label="Keypad"
          aria-pressed={keypad}
          onclick={() => (keypad = !keypad)}
        >
          <span class="round"><Icon name="dialpad" size={26} /></span>
        </button>
        <button
          class="action end"
          aria-label="End call"
          disabled={!!call.busy}
          onclick={() => hangup(lead)}
        >
          <span class="round">
            {#if call.busy === 'hangup'}
              <Spinner size={22} label="Ending" />
            {:else}
              <Icon name="phone-off" size={28} />
            {/if}
          </span>
        </button>
      {:else if lead.state !== 'ended'}
        <!-- Calling, ringing at the other end, or only a held call
             left: ending is what there is to do. -->
        <button
          class="action end"
          aria-label="End call"
          disabled={!!call.busy}
          onclick={() => hangup(lead)}
        >
          <span class="round">
            {#if call.busy === 'hangup'}
              <Spinner size={22} label="Ending" />
            {:else}
              <Icon name="phone-off" size={28} />
            {/if}
          </span>
        </button>
      {/if}
    </div>
  </section>
{/if}

<style>
  .card {
    position: fixed;
    /* Centred on the screen area to the right of the rail, not on the
       whole window: the rail is 120px. */
    left: calc(120px + (100vw - 120px) / 2);
    /* Under the 64px status bar, with a little air. */
    top: calc(64px + 12px);
    z-index: 50;
    display: flex;
    flex-direction: column;
    gap: var(--spacing);
    width: min(520px, calc(100vw - 120px - 32px));
    padding: var(--spacing) var(--spacing-l);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 8px 32px rgb(0 0 0 / 0.45);
    transform: translateX(-50%);
    animation: rise 0.22s ease-out;
  }

  /* Ringing: a band of the ringing colour along the top, so the card
     reads as "wants an answer" before anything on it is read. */
  .card.ringing {
    border-top: 4px solid var(--call-ring);
  }

  .card.ended {
    border-top: 4px solid var(--call-end);
  }

  @keyframes rise {
    from {
      opacity: 0;
      transform: translate(-50%, -24px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .card {
      animation: none;
    }
  }

  header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--spacing);
  }

  .photo {
    width: 64px;
    height: 64px;
    object-fit: cover;
    border-radius: 50%;
  }

  .who {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .name {
    overflow: hidden;
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 700;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .detail {
    overflow: hidden;
    font-size: 14px;
    color: var(--text-dim);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .state {
    font-size: 15px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .state.live {
    font-weight: 600;
    color: var(--call-live);
  }

  .ended .state {
    font-weight: 600;
    color: var(--call-end);
  }

  .minimize {
    display: grid;
    place-items: center;
    width: 48px;
    height: 48px;
    align-self: start;
    color: var(--text-dim);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  .others {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .others li {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--spacing-s);
    padding: 6px 10px;
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .other-name {
    overflow: hidden;
    font-weight: 600;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .other-state {
    font-size: 13px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .keypad {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
  }

  .typed {
    min-height: 32px;
    font-family: var(--font-display);
    font-size: 24px;
    letter-spacing: 0.12em;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }

  .typed.empty {
    font-family: var(--font-body);
    font-size: 14px;
    letter-spacing: 0;
    color: var(--text-faint);
  }

  .keys {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }

  .key {
    height: 52px;
    font-family: var(--font-display);
    font-size: 22px;
    font-weight: 600;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .error {
    margin: 0;
    font-size: 14px;
    text-align: center;
    color: var(--danger);
  }

  .actions {
    display: flex;
    justify-content: center;
    gap: 40px;
  }

  .actions:empty {
    display: none;
  }

  /* Round buttons, icon only -- the colours and icons are the ones
     every phone uses, and the words under them were reading matter
     where a glance should do. Big enough to hit without looking for
     long; named for screen readers by aria-label. */
  .action {
    display: grid;
    padding: 0;
    color: var(--text);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .round {
    display: grid;
    place-items: center;
    width: 64px;
    height: 64px;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 50%;
  }

  .answer .round {
    color: #fff;
    background: var(--call-live);
    border-color: transparent;
  }

  .end .round {
    color: #fff;
    background: var(--call-end);
    border-color: transparent;
  }

  .toggle.on .round {
    color: var(--bg);
    background: var(--text);
  }

  .action:disabled {
    opacity: 0.6;
  }

  .action:active:not(:disabled) .round,
  .key:active,
  .minimize:active {
    filter: brightness(0.9);
  }

  button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }
</style>
