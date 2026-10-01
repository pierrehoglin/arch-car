<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Button from '$lib/ui/Button.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Dialog from '$lib/ui/Dialog.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Slider from '$lib/ui/Slider.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import Switch from '$lib/ui/Switch.svelte'
  import {
    GAIN_MAX,
    GAIN_MIN,
    forgetPreset,
    loadPresets,
    loadSettings,
    radio,
    refresh,
    setSetting,
    watch,
  } from '$lib/radio.svelte'
  import { isDark } from '$lib/settings.svelte'
  import { logoForPi, nameForPi, referenceOf } from '$lib/stations'
  import type { Station } from '$lib/api/types'

  /* The radio is not followed by the root layout, so this screen
     subscribes for itself -- the list should notice a station saved
     from the radio screen, and "on air" should move when it is
     retuned. */
  $effect(() => {
    refresh()
    loadPresets()
    loadSettings()
    return watch()
  })

  /* Where the gain thumb is while it is held. Saving happens on
     release, because applying a gain restarts the receiver and doing
     that per pixel of a drag would be unusable. */
  let dragging = $state<number | null>(null)
  const gain = $derived(dragging ?? radio.settings.gain)

  /* Which station is waiting on the confirmation. Confirmed rather
     than removed on the tap: the PI and alternates were recorded
     while it was playing, and getting them back means tuning it in
     again. */
  let forgetting = $state<Station | null>(null)

  const mhz = (frequency: number) => `${frequency.toFixed(1)} MHz`

  /** What to call a station: its saved name, then what its PI says,
   *  then just where it is. */
  const titleOf = (station: Station) =>
    station.name || nameForPi(station.pi) || mhz(station.frequency)

  const onAir = (station: Station) =>
    radio.state.playing &&
    radio.state.frequency !== null &&
    Math.abs(radio.state.frequency - station.frequency) < 0.05

  const lastStation = $derived.by(() => {
    const last = radio.state.last
    if (last === null) return ''
    const preset = radio.presets.find(
      (station) => Math.abs(station.frequency - last) < 0.05,
    )
    return preset ? `${titleOf(preset)} · ${mhz(last)}` : mhz(last)
  })
</script>

<Card eyebrow="Radio" gap="none" trim>
  <Row
    title="Start on boot"
    detail="Turn the radio on when the car starts"
  >
    <Switch
      label="Start on boot"
      checked={radio.settings.autostart}
      onchange={(on) => setSetting('autostart', on)}
    />
  </Row>

  <Row
    title="RDS"
    detail="Station names, radio text and traffic flags. Off uses less CPU."
  >
    <Switch
      label="RDS"
      checked={radio.settings.rds}
      disabled={radio.applying}
      onchange={(on) => setSetting('rds', on)}
    />
  </Row>

  <!-- Traffic announcements are flagged in RDS, so without it there is
       nothing to listen for. Disabled rather than hidden, so the
       setting does not vanish from under a finger. -->
  <Row
    title="Traffic announcements"
    detail={radio.settings.rds
      ? 'Interrupt whatever is playing for traffic news'
      : 'Needs RDS'}
  >
    <Switch
      label="Traffic announcements"
      checked={radio.settings.traffic && radio.settings.rds}
      disabled={!radio.settings.rds}
      onchange={(on) => setSetting('traffic', on)}
    />
  </Row>

  <Row
    title="Tuner gain"
    detail={radio.applying
      ? 'Restarting the radio to apply'
      : 'Lower suits a car antenna; a bare wire wants about 40'}
  >
    {#if radio.applying}
      <Spinner size={20} label="Applying" />
    {/if}
    <div class="gain">
      <Slider
        label="Tuner gain"
        min={GAIN_MIN}
        max={GAIN_MAX}
        step={1}
        value={gain}
        readout="{gain} dB"
        disabled={radio.applying}
        oninput={(value) => (dragging = value)}
        onchange={(value) => {
          dragging = null
          if (value !== radio.settings.gain) setSetting('gain', value)
        }}
      />
    </div>
  </Row>

  {#if lastStation}
    <Row title="Last station" detail="Where the radio comes back on">
      <span class="value">{lastStation}</span>
    </Row>
  {/if}
</Card>

<Card eyebrow="Saved stations" gap="s">
  <div class="head">
    <span class="count">
      {#if radio.presets.length === 1}
        1 saved
      {:else if radio.presets.length}
        {radio.presets.length} saved
      {:else}
        Nothing saved yet
      {/if}
    </span>

    <!-- Naming and ordering live on the radio screen, where the
         stations are played from. This list is for seeing what was
         recorded, and for clearing out. -->
    <a class="link" href="/media/fm">
      Open radio
      <Icon name="chevron-right" size={16} />
    </a>
  </div>

  {#if radio.presets.length}
    <ul class="stations">
      {#each radio.presets as station (station.frequency)}
        {@const logo = station.pi ? logoForPi(station.pi, isDark()) : ''}
        {@const known = nameForPi(station.pi)}
        <li class="station" class:live={onAir(station)}>
          <!-- The logo where there is one, the frequency where not --
               the same thing the radio screen shows in that place. -->
          <span class="mark">
            {#if logo}
              <img src={logo} alt="" />
            {:else}
              <span class="dial">{station.frequency.toFixed(1)}</span>
            {/if}
          </span>

          <div class="info">
            <div class="top">
              <span class="name">{titleOf(station)}</span>
              <span class="freq">{mhz(station.frequency)}</span>
              {#if onAir(station)}
                <span class="badge">On air</span>
              {/if}
            </div>

            {#if station.pi || station.ecc || station.alt_frequencies.length}
              <dl class="facts">
                {#if station.pi}
                  <div>
                    <dt>PI</dt>
                    <dd>
                      {referenceOf(station.pi)
                        ? station.pi.replace(/^0x/i, '').toUpperCase()
                        : station.pi}
                      {#if known && known !== titleOf(station)}
                        · {known}
                      {/if}
                    </dd>
                  </div>
                {/if}
                {#if station.ecc}
                  <div>
                    <dt>ECC</dt>
                    <dd>{station.ecc}</dd>
                  </div>
                {/if}
                {#if station.alt_frequencies.length}
                  <div>
                    <dt>Also on</dt>
                    <dd>
                      {station.alt_frequencies
                        .map((f) => f.toFixed(1))
                        .join(' · ')} MHz
                    </dd>
                  </div>
                {/if}
              </dl>
            {:else}
              <p class="missing">
                No RDS recorded. It is captured when a station is saved
                while it is playing.
              </p>
            {/if}
          </div>

          <Button
            variant="quiet"
            square
            label="Forget {titleOf(station)}"
            onclick={() => (forgetting = station)}
          >
            <Icon name="trash" size={20} />
          </Button>
        </li>
      {/each}
    </ul>
  {/if}

  {#if radio.error}
    <p class="warning">{radio.error}</p>
  {/if}
</Card>

<Dialog
  open={!!forgetting}
  title="Forget"
  width={480}
  onclose={() => (forgetting = null)}
>
  {#if forgetting}
    <p class="confirm">
      Forget <strong>{titleOf(forgetting)}</strong>?
    </p>
    <p class="confirm detail">
      What was recorded about it goes too. Saving it again picks that
      back up only while it is playing.
    </p>
  {/if}

  {#snippet footer()}
    <Button variant="quiet" onclick={() => (forgetting = null)}>Keep</Button>
    <Button
      variant="danger"
      onclick={() => {
        if (forgetting) forgetPreset(forgetting.frequency)
        forgetting = null
      }}
    >
      Forget
    </Button>
  {/snippet}
</Dialog>

<style>
  .gain {
    width: 260px;
  }

  .value {
    font-size: 15px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
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
    font-variant-numeric: tabular-nums;
  }

  .link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-height: 46px;
    padding: 0 var(--spacing-xs);
    font-size: 14px;
    font-weight: 600;
    color: var(--accent);
    text-decoration: none;
  }

  .stations {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .station {
    display: flex;
    align-items: center;
    gap: var(--spacing);
    min-height: 78px;
    padding: var(--spacing-s) var(--spacing);
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .station.live {
    border-color: var(--accent);
  }

  /* A fixed box, so names line up whether a row has a logo, a
     frequency, or a logo of some other shape. Height set on the image
     too: an SVG with no intrinsic size otherwise collapses to nothing. */
  .mark {
    display: grid;
    place-items: center;
    flex: none;
    width: 76px;
    height: 48px;
  }

  .mark img {
    max-width: 100%;
    height: 48px;
    object-fit: contain;
  }

  .dial {
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 700;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .info {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  .top {
    display: flex;
    align-items: baseline;
    gap: var(--spacing-s);
    min-width: 0;
  }

  .name {
    overflow: hidden;
    font-size: 16px;
    font-weight: 600;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .freq {
    flex: none;
    font-size: 13px;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .badge {
    flex: none;
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--accent);
  }

  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 4px var(--spacing-l);
    margin: 0;
    font-size: 13px;
  }

  .facts div {
    display: flex;
    gap: 6px;
  }

  .facts dt {
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.16em;
    line-height: 19px;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .facts dd {
    margin: 0;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .missing {
    margin: 0;
    font-size: 13px;
    color: var(--text-faint);
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
