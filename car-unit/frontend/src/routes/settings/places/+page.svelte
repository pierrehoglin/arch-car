<script lang="ts">
  import Icon from '$lib/Icon.svelte';
  import Button from '$lib/ui/Button.svelte';
  import Card from '$lib/ui/Card.svelte';
  import Dialog from '$lib/ui/Dialog.svelte';
  import Row from '$lib/ui/Row.svelte';
  import Spinner from '$lib/ui/Spinner.svelte';
  import * as places from '$lib/api/places';
  import { RequestFailed } from '$lib/api/client';
  import type { Place } from '$lib/api/types';

  /* Places the car knows by name -- home, work, the summer house --
     and where it is now. Saved places are what the weather offers to
     switch between, and what navigation will offer as destinations.

     Fetched on opening rather than followed: places change when
     someone saves one, which is not something that happens while
     this screen is being looked at. */

  let saved = $state<Place[]>([]);
  let here = $state<Place | null>(null);
  let loading = $state(true);
  let error = $state('');

  /** Which place is waiting on the confirmation. */
  let forgetting = $state<Place | null>(null);
  let removing = $state(false);

  function report(cause: unknown): void {
    error =
      cause instanceof RequestFailed || cause instanceof Error ? cause.message : String(cause);
  }

  $effect(() => {
    load();
  });

  async function load(): Promise<void> {
    loading = true;
    try {
      /* Separately: the position can fail -- no fix yet -- without
         that hiding the list. */
      const [list, now] = await Promise.allSettled([places.saved(), places.current()]);
      if (list.status === 'fulfilled') saved = list.value;
      else report(list.reason);
      here = now.status === 'fulfilled' ? now.value : null;
    } finally {
      loading = false;
    }
  }

  async function forget(place: Place): Promise<void> {
    removing = true;
    error = '';
    try {
      saved = await places.forget(place.name);
    } catch (cause) {
      report(cause);
    } finally {
      removing = false;
      forgetting = null;
    }
  }

  /** 59.3293, 18.0686 -- four decimals is about ten metres. */
  const coordinates = (place: Place) =>
    `${place.latitude.toFixed(4)}, ${place.longitude.toFixed(4)}`;

  /** The house for home, a pin for the rest. */
  const iconFor = (place: Place) => (/^(home|hem|hemma)$/i.test(place.name) ? 'home' : 'map');
</script>

<Card eyebrow="Where the car is" gap="none" trim>
  {#if loading}
    <Row title="Finding the position…">
      <Spinner size={20} label="Loading" />
    </Row>
  {:else if here}
    <Row
      title={here.address || 'Position known'}
      detail={here.address ? coordinates(here) : `${coordinates(here)} · no address looked up yet`}
    >
      <Icon name="crosshair" size={22} />
    </Row>
  {:else}
    <Row
      title="No position yet"
      detail="Waiting for a GPS fix. A cold start can take a few minutes."
    />
  {/if}
</Card>

<Card eyebrow="Saved places" gap="s">
  {#if loading}
    <p class="empty">Loading…</p>
  {:else if !saved.length}
    <p class="empty">
      Nothing saved yet. Places are saved from the car with
      <code>places save &lt;name&gt;</code>, which stores where it is now.
    </p>
  {:else}
    <ul class="places">
      {#each saved as place (place.name)}
        <li class="place">
          <span class="mark">
            <Icon name={iconFor(place)} size={22} />
          </span>

          <span class="text">
            <span class="name">{place.name}</span>
            {#if place.address}
              <span class="address">{place.address}</span>
            {/if}
            <span class="where">
              {coordinates(place)}
              {#if place.altitude !== null}
                · {Math.round(place.altitude)} m above sea level
              {/if}
            </span>
          </span>

          <Button
            variant="quiet"
            square
            label="Forget {place.name}"
            disabled={removing}
            onclick={() => (forgetting = place)}
          >
            <Icon name="trash" size={20} />
          </Button>
        </li>
      {/each}
    </ul>
  {/if}

  {#if error}
    <p class="warning">{error}</p>
  {/if}
</Card>

<Dialog open={!!forgetting} title="Forget" width={480} onclose={() => (forgetting = null)}>
  {#if forgetting}
    <p class="confirm">Forget <strong>{forgetting.name}</strong>?</p>
    <p class="confirm detail">It disappears from the weather's list of places too.</p>
  {/if}

  {#snippet footer()}
    <Button variant="quiet" onclick={() => (forgetting = null)}>Keep</Button>
    <Button
      variant="danger"
      working={removing}
      disabled={removing}
      onclick={() => forgetting && forget(forgetting)}
    >
      Forget
    </Button>
  {/snippet}
</Dialog>

<style>
  .places {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .place {
    display: flex;
    align-items: center;
    gap: var(--spacing);
    min-height: 72px;
    padding: var(--spacing-s) var(--spacing);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .mark {
    display: grid;
    place-items: center;
    flex: none;
    width: 40px;
    height: 40px;
    color: var(--accent);
    background: var(--accent-soft);
    border-radius: 50%;
  }

  .text {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .name {
    font-size: 16px;
    font-weight: 600;
  }

  .address,
  .where {
    overflow: hidden;
    font-size: 13px;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .address {
    color: var(--text-dim);
  }

  .where {
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .empty {
    margin: 0;
    padding: var(--spacing-xs) 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-dim);
  }

  code {
    font-size: 13px;
    color: var(--text);
  }

  .warning {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }

  .confirm {
    margin: 0 0 var(--spacing-s);
    font-size: 16px;
  }

  .confirm.detail {
    font-size: 14px;
    color: var(--text-dim);
  }
</style>
