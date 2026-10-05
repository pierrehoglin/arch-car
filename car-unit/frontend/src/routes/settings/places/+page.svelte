<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Button from '$lib/ui/Button.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Dialog from '$lib/ui/Dialog.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Slider from '$lib/ui/Slider.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import Switch from '$lib/ui/Switch.svelte'
  import KeyboardInput from '$lib/ui/KeyboardInput.svelte'
  import * as places from '$lib/api/places'
  import * as stored from '$lib/api/settings'
  import { RequestFailed } from '$lib/api/client'
  import type { Address, Place } from '$lib/api/types'
  import { distinguish } from '$lib/address'

  /* Places the car knows by name -- home, work, the summer house --
     and where it is now. Saved places are what the weather offers to
     switch between, and what navigation will offer as destinations.

     Fetched on opening rather than followed: places change when
     someone saves one, which is not something that happens while
     this screen is being looked at. */

  let saved = $state<Place[]>([])
  let here = $state<Place | null>(null)
  let loading = $state(true)
  let error = $state('')

  /** Which place is waiting on the confirmation. */
  let forgetting = $state<Place | null>(null)
  let removing = $state(false)

  function report(cause: unknown): void {
    error =
      cause instanceof RequestFailed || cause instanceof Error
        ? cause.message
        : String(cause)
  }

  $effect(() => {
    load()
  })

  async function load(): Promise<void> {
    loading = true
    try {
      /* Separately: the position can fail -- no fix yet -- without
         that hiding the list. */
      const [list, now] = await Promise.allSettled([
        places.saved(),
        places.current(),
      ])
      if (list.status === 'fulfilled') saved = list.value
      else report(list.reason)
      here = now.status === 'fulfilled' ? now.value : null
    } finally {
      loading = false
    }
  }

  async function forget(place: Place): Promise<void> {
    removing = true
    error = ''
    try {
      saved = await places.forget(place.name)
    } catch (cause) {
      report(cause)
    } finally {
      removing = false
      forgetting = null
    }
  }

  /** 59.3293, 18.0686 -- four decimals is about ten metres. */
  const coordinates = (place: Place) =>
    `${place.latitude.toFixed(4)}, ${place.longitude.toFixed(4)}`

  /* Address lookup settings, read from the daemon's catalogue so the
     defaults live in one place -- carlib/core/settings.py -- rather
     than being repeated here. Each control writes its key alone, on
     release for the sliders. */
  let geo = $state<Record<string, unknown>>({})
  let geoDefaults = $state<Record<string, unknown>>({})

  $effect(() => {
    stored
      .catalogue()
      .then((entries) => {
        const values: Record<string, unknown> = {}
        const defaults: Record<string, unknown> = {}
        for (const entry of entries) {
          if (!entry.key.startsWith('geocoding.')) continue
          defaults[entry.key] = entry.default
          values[entry.key] = entry.set ? entry.value : entry.default
        }
        geoDefaults = defaults
        geo = values
      })
      .catch(report)
  })

  async function setGeo(key: string, value: unknown): Promise<void> {
    const previous = geo[key]
    geo[key] = value
    try {
      await stored.update({ [key]: value })
    } catch (cause) {
      geo[key] = previous
      report(cause)
    }
  }

  const num = (key: string) => Number(geo[key] ?? geoDefaults[key] ?? 0)
  const text = (key: string) => String(geo[key] ?? '')
  const flag = (key: string) => geo[key] === true

  const metres = (value: number) =>
    value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value} m`

  const seconds = (value: number) =>
    value >= 60 ? `${Math.round(value / 6) / 10} min` : `${value} s`

  /** "12 min ago", for a last known position. */
  function ago(seconds: number | null | undefined): string {
    if (!seconds) return ''
    const minutes = Math.max(0, Math.round((Date.now() / 1000 - seconds) / 60))
    if (minutes < 1) return 'just now'
    if (minutes < 60) return `${minutes} min ago`
    const hours = Math.round(minutes / 60)
    if (hours < 48) return `${hours} h ago`
    return `${Math.round(hours / 24)} days ago`
  }

  /* --- Adding a place ---------------------------------------------

     Two steps in one dialog: find where, then name it. Where is a
     search result or the car's own position; the name is free, and
     an existing name is replaced rather than duplicated -- the daemon
     keys places by name. */

  let adding = $state(false)
  let query = $state('')
  let results = $state<Address[]>([])
  let searching = $state(false)
  let searched = $state(false)
  let picked = $state<{
    latitude: number
    longitude: number
    address: string
    /** What the chosen result was, for the name step. */
    kind?: string
  } | null>(null)
  let newName = $state('')
  let saving = $state(false)
  let addError = $state('')

  function openAdd(): void {
    adding = true
    query = ''
    results = []
    searched = false
    picked = null
    newName = ''
    addError = ''
  }

  /* On Done rather than per letter: the keyboard buffers what is
     typed, and the suggestion service is rate limited -- one search
     per finished query is both what the field gives and what the
     service wants. */
  async function runSearch(text: string): Promise<void> {
    query = text
    addError = ''
    const trimmed = text.trim()
    if (trimmed.length < places.MIN_CHARS) {
      results = []
      searched = false
      return
    }
    searching = true
    try {
      results = await places.suggest(trimmed, 8)
    } catch (cause) {
      results = []
      addError =
        cause instanceof Error ? cause.message : 'The search did not answer'
    } finally {
      searching = false
      searched = true
    }
  }

  /** The line worth reading first: a name, or the street. */
  function titleOf(found: Address): string {
    if (found.name) return found.name
    return [found.road, found.house_number].filter(Boolean).join(' ')
      || found.display_name.split(', ')[0]
  }

  /** Where it is, short: the town, or the municipality. */
  function townOf(found: Address): string {
    return found.city || found.municipality || found.county || ''
  }

  function pick(found: Address): void {
    picked = {
      latitude: found.latitude,
      longitude: found.longitude,
      address: [titleOf(found), townOf(found)].filter(Boolean).join(', '),
      kind: distinguish(found, null),
    }
    newName = found.name || ''
  }

  function pickCar(): void {
    if (!here) return
    picked = {
      latitude: here.latitude,
      longitude: here.longitude,
      address: here.address,
    }
    newName = ''
  }

  const replaces = $derived(
    saved.some(
      (place) => place.name.toLowerCase() === newName.trim().toLowerCase(),
    ),
  )

  async function saveNew(): Promise<void> {
    if (!picked || !newName.trim()) return
    saving = true
    addError = ''
    try {
      saved = await places.save({
        name: newName.trim(),
        latitude: picked.latitude,
        longitude: picked.longitude,
        address: picked.address,
        /* Looked up only when there is nothing to show: a search
           result already has its address, and the car's position
           usually does. */
        lookup: !picked.address,
      })
      adding = false
    } catch (cause) {
      addError = cause instanceof Error ? cause.message : String(cause)
    } finally {
      saving = false
    }
  }

  /** The house for home, a pin for the rest. */
  const iconFor = (place: Place) =>
    /^(home|hem|hemma)$/i.test(place.name) ? 'home' : 'map'
</script>

<Card eyebrow="Where the car is" gap="none" trim>
  {#if loading}
    <Row title="Finding the position…">
      <Spinner size={20} label="Loading" />
    </Row>
  {:else if here?.last_known}
    <!-- The GPS has no fix yet; this is where the car last had one.
         Said, rather than shown as if it were live. -->
    <Row
      title={here.address || 'Last known position'}
      detail={`${coordinates(here)} · last known ${ago(here.at)} · waiting for GPS`}
    >
      <Icon name="crosshair" size={22} />
    </Row>
  {:else if here}
    <Row
      title={here.address || 'Position known'}
      detail={here.address
        ? coordinates(here)
        : `${coordinates(here)} · no address looked up yet`}
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
  <div class="head">
    <span class="count">
      {#if !loading}
        {saved.length === 1 ? '1 place' : `${saved.length} places`}
      {/if}
    </span>
    <Button variant="quiet" disabled={loading} onclick={openAdd}>
      <Icon name="add" size={18} />
      Add
    </Button>
  </div>

  {#if loading}
    <p class="empty">Loading…</p>
  {:else if !saved.length}
    <p class="empty">
      Nothing saved yet. Add home, work or anywhere else you go, by
      address or where the car is now.
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

<!-- How the address of where the car is gets looked up. Only the
     automatic lookup is off by default: it uses a public service with
     a usage policy, so turning it on is a deliberate choice. -->
<Card eyebrow="Address lookup" gap="none" trim>
  <Row
    title="Follow the car"
    detail="Look up the address as the car moves, at most 4 times a minute. Uses the internet."
  >
    <Switch
      label="Follow the car"
      checked={flag('geocoding.auto')}
      onchange={(on) => setGeo('geocoding.auto', on)}
    />
  </Row>

  <Row
    title="Look up after"
    detail="Distance moved before the address is looked up again"
  >
    <div class="slider">
      <Slider
        label="Distance before looking up again"
        min={100}
        max={5000}
        step={100}
        value={num('geocoding.move_metres')}
        readout={metres(num('geocoding.move_metres'))}
        oninput={(value) => (geo['geocoding.move_metres'] = value)}
        onchange={(value) => setGeo('geocoding.move_metres', value)}
      />
    </div>
  </Row>

  <!-- The two below work together: a short move counts once the
       address has gone stale, so turning off a main road updates it
       without a full kilometre of driving. -->
  <Row
    title="Or, once stale, after"
    detail="A shorter move that is enough once the address is old"
  >
    <div class="slider">
      <Slider
        label="Short move once stale"
        min={10}
        max={500}
        step={10}
        value={num('geocoding.min_move_metres')}
        readout={metres(num('geocoding.min_move_metres'))}
        oninput={(value) => (geo['geocoding.min_move_metres'] = value)}
        onchange={(value) => setGeo('geocoding.min_move_metres', value)}
      />
    </div>
  </Row>

  <Row title="Stale after" detail="How old the address is before a short move counts">
    <div class="slider">
      <Slider
        label="Address is stale after"
        min={30}
        max={600}
        step={30}
        value={num('geocoding.stale_seconds')}
        readout={seconds(num('geocoding.stale_seconds'))}
        oninput={(value) => (geo['geocoding.stale_seconds'] = value)}
        onchange={(value) => setGeo('geocoding.stale_seconds', value)}
      />
    </div>
  </Row>

  <Row
    title="Nearby first"
    detail="Rank search suggestions near the car first. Off when searching somewhere else."
  >
    <Switch
      label="Nearby first"
      checked={flag('geocoding.bias')}
      onchange={(on) => setGeo('geocoding.bias', on)}
    />
  </Row>

  <Row
    title="Search in country"
    detail="Two-letter country code for address searches. Empty searches everywhere."
  >
    <div class="field short">
      <KeyboardInput
        value={text('geocoding.country')}
        label="Country code"
        placeholder="Everywhere"
        maxlength={2}
        onchange={(value) =>
          setGeo('geocoding.country', value.trim().toLowerCase())}
      />
    </div>
  </Row>

  <Row
    title="Suggestion server"
    detail="Photon server for type-ahead suggestions"
  >
    <div class="field">
      <KeyboardInput
        value={text('geocoding.photon_url')}
        label="Suggestion server"
        placeholder={String(geoDefaults['geocoding.photon_url'] ?? '')}
        maxlength={120}
        onchange={(value) =>
          setGeo(
            'geocoding.photon_url',
            value.trim() || geoDefaults['geocoding.photon_url'],
          )}
      />
    </div>
  </Row>
</Card>

<Dialog
  open={adding}
  title={picked ? 'Name the place' : 'Add a place'}
  width={640}
  onclose={() => (adding = false)}
>
  {#if !picked}
    <div class="add">
      <KeyboardInput
        value={query}
        label="Search"
        placeholder="Address or place"
        maxlength={64}
        onchange={runSearch}
      />

      {#if here}
        <Button variant="quiet" onclick={pickCar}>
          <Icon name="crosshair" size={18} />
          Use where the car is{here.last_known ? ' (last known)' : ''}
        </Button>
      {/if}

      {#if searching}
        <p class="note"><Spinner size={16} label="Searching" /> Searching…</p>
      {:else if results.length}
        <ul class="results">
          {#each results as found (found.osm_id || `${found.latitude},${found.longitude}`)}
            <li>
              <button class="result" onclick={() => pick(found)}>
                <span class="result-title">{titleOf(found)}</span>
                <span class="result-detail">{found.display_name}</span>
                <!-- What tells it from the others: several results can
                     share a street address, being the address point,
                     the building and a business inside it. -->
                <span class="result-kind">{distinguish(found, here)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else if searched}
        <p class="note">Nothing found for “{query}”.</p>
      {:else}
        <p class="note">
          Type at least {places.MIN_CHARS} letters and press Done to search.
        </p>
      {/if}
    </div>
  {:else}
    <div class="add">
      <div class="chosen">
        <span class="chosen-title">{picked.address || 'Where the car is'}</span>
        <span class="chosen-where">
          {[picked.kind, `${picked.latitude.toFixed(4)}, ${picked.longitude.toFixed(4)}`]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </div>

      <KeyboardInput
        value={newName}
        label="Name"
        placeholder="Home, Work, Sommarstugan…"
        maxlength={32}
        onchange={(value) => (newName = value)}
      />

      {#if replaces}
        <p class="note">Replaces the saved place with this name.</p>
      {/if}
    </div>
  {/if}

  {#if addError}
    <p class="warning">{addError}</p>
  {/if}

  {#snippet footer()}
    {#if picked}
      <Button variant="quiet" onclick={() => (picked = null)}>Back</Button>
      <Button
        variant="primary"
        working={saving}
        disabled={saving || !newName.trim()}
        onclick={saveNew}
      >
        Save
      </Button>
    {:else}
      <Button variant="quiet" onclick={() => (adding = false)}>Cancel</Button>
    {/if}
  {/snippet}
</Dialog>

<Dialog
  open={!!forgetting}
  title="Forget"
  width={480}
  onclose={() => (forgetting = null)}
>
  {#if forgetting}
    <p class="confirm">Forget <strong>{forgetting.name}</strong>?</p>
    <p class="confirm detail">
      It disappears from the weather's list of places too.
    </p>
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

  .warning {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }

  .slider {
    width: 260px;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
    min-height: 46px;
  }

  .count {
    font-size: 13px;
    color: var(--text-dim);
  }

  .add {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
  }

  .note {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    margin: 0;
    font-size: 13px;
    color: var(--text-dim);
  }

  .results {
    max-height: 320px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .result {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    min-height: 62px;
    padding: var(--spacing-s) var(--spacing);
    text-align: left;
    background: none;
    border: 0;
    border-bottom: 1px solid var(--hairline);
  }

  .results li:last-child .result {
    border-bottom: 0;
  }

  .result:active {
    background: var(--panel-2);
  }

  .result-title {
    font-size: 16px;
    font-weight: 600;
  }

  .result-detail {
    overflow: hidden;
    font-size: 12.5px;
    color: var(--text-dim);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .result-kind {
    font-size: 12.5px;
    color: var(--text-faint);
  }

  .chosen {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--spacing-s) var(--spacing);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .chosen-title {
    font-size: 16px;
    font-weight: 600;
  }

  .chosen-where {
    font-size: 13px;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .field {
    width: 300px;
  }

  .field.short {
    width: 140px;
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
