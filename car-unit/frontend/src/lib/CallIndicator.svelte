<script lang="ts">
  import Icon from './Icon.svelte'
  import { call, duration, live, main, show } from './call.svelte'

  /* The call in the status bar: there for as long as a call is, open
     card or not, so its state is always in the same place. Tapping it
     brings the card back.

     An icon only, in the call's colour -- amber while ringing or
     calling, green once connected (with how long), red once ended --
     and gone a moment after that, with the call. */

  const lead = $derived(main())

  /* Connected, or on hold with nothing else going on: green, timed by
     whichever call is connected. */
  const connected = $derived(live().find((c) => c.state === 'active') ?? null)

  const look = $derived.by(() => {
    if (!lead) return null
    switch (lead.state) {
      case 'incoming':
      case 'waiting':
        return { kind: 'ring', icon: 'call-in', label: 'Incoming call' }
      case 'dialing':
      case 'alerting':
        return { kind: 'ring', icon: 'call-out', label: 'Calling' }
      case 'active':
      case 'held':
        return { kind: 'live', icon: 'phone', label: 'In a call' }
      default:
        return { kind: 'end', icon: 'phone-off', label: 'Call ended' }
    }
  })

  const time = $derived(
    look?.kind === 'live' && connected ? duration(connected) : '',
  )
</script>

{#if look && call.status.calls.length}
  <button
    class="indicator {look.kind}"
    aria-label="{look.label}{time ? `, ${time}` : ''}. Show the call"
    onclick={show}
  >
    <span class="badge"><Icon name={look.icon} size={18} /></span>
    {#if time}
      <span class="time">{time}</span>
    {/if}
  </button>
{/if}

<style>
  .indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 40px;
    padding: 0;
    color: var(--text);
    background: none;
    border: 0;
  }

  .badge {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    color: #fff;
    border-radius: 50%;
  }

  .ring .badge {
    background: var(--call-ring);
    animation: ring 1.2s ease-in-out infinite;
  }

  .live .badge {
    background: var(--call-live);
  }

  .end .badge {
    background: var(--call-end);
  }

  .time {
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--call-live);
    font-variant-numeric: tabular-nums;
  }

  /* Ringing pulses gently: the one state that is waiting on someone. */
  @keyframes ring {
    50% {
      transform: scale(1.12);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .ring .badge {
      animation: none;
    }
  }

  .indicator:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 999px;
  }
</style>
