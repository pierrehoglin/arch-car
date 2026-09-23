<script lang="ts">
  import Button from './Button.svelte'
  import Dialog from './Dialog.svelte'
  import { answer, bluetooth } from '../bluetooth.svelte'

  /* The numeric comparison.
   *
   * BlueZ hands the decision to the agent in the daemon, which holds
   * its call open until this answers. Nothing else can pair a phone:
   * without an answer the request expires and the phone reports that
   * pairing failed.
   *
   * Lives in the root layout rather than on the connectivity screen,
   * because a phone can start pairing at any moment and whoever is
   * driving is unlikely to be on that screen when it does.
   */

  /* The daemon gives up at 28 seconds. Counted here from when the
     request arrived, which is a moment later than the daemon started
     waiting -- so this runs out slightly early, which is the right
     way round for a countdown. */
  const LIMIT = 28

  const request = $derived(bluetooth.request)

  let left = $state(LIMIT)

  $effect(() => {
    if (!request) return

    left = LIMIT
    const timer = setInterval(() => {
      left = Math.max(0, left - 1)
    }, 1000)

    return () => clearInterval(timer)
  })
</script>

<Dialog
  open={!!request}
  title="Pair"
  width={480}
  onclose={() => answer(false)}
>
  {#if request}
    <div class="body">
      <p class="who">
        <strong>{request.name}</strong> wants to pair
      </p>

      {#if request.passkey}
        <p class="code">{request.passkey}</p>
        <p class="detail">
          Check the phone is showing the same number.
        </p>
      {:else}
        <!-- Just Works: the other side has no display, so there is
             nothing to compare and only a yes or no to give. -->
        <p class="detail">
          This device cannot show a code, so there is nothing to
          compare. Only accept it if you started this.
        </p>
      {/if}

      <p class="clock" class:soon={left <= 10}>
        {#if left > 0}
          {left}s to answer
        {:else}
          Time is up — the phone has probably given up
        {/if}
      </p>
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="quiet" onclick={() => answer(false)}>Reject</Button>
    <Button variant="primary" onclick={() => answer(true)}>Confirm</Button>
  {/snippet}
</Dialog>

<style>
  .body {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--spacing-s);
    padding: var(--spacing-s) 0 var(--spacing-l);
    text-align: center;
  }

  .who {
    margin: 0;
    font-size: 16px;
    color: var(--text-dim);
  }

  .who strong {
    color: var(--text);
  }

  /* Large and spaced: it is read off one screen and compared with
     another, a digit at a time. */
  .code {
    margin: var(--spacing-xs) 0;
    font-family: var(--font-display);
    font-size: 52px;
    font-weight: 600;
    letter-spacing: 0.16em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    /* The letter-spacing is on the right of each digit, which throws
       the block off centre without this. */
    text-indent: 0.16em;
  }

  .detail {
    max-width: 34ch;
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-dim);
  }

  .clock {
    margin: var(--spacing-xs) 0 0;
    font-size: 12px;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .clock.soon {
    color: var(--danger);
  }
</style>
