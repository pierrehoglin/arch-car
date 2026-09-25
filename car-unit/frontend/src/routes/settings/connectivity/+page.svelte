<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Button from '$lib/ui/Button.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Dialog from '$lib/ui/Dialog.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import Switch from '$lib/ui/Switch.svelte'
  import {
    bluetooth,
    busyWith,
    connect,
    connected,
    devices,
    disconnect,
    forget,
    iconFor,
    pair,
    searching,
    setService,
    toggleSearch,
  } from '$lib/bluetooth.svelte'
  import type { BtDevice } from '$lib/api/types'
  import Segmented from '$lib/ui/Segmented.svelte'
  import KeyboardInput from '$lib/ui/KeyboardInput.svelte'
  import hotspotQr from '$lib/assets/hotspot-qr.svg'
  import {
    disconnect as leaveWifi,
    forget as forgetWifi,
    join,
    mode,
    network,
    networks,
    refresh as refreshNetwork,
    scan,
    secured,
    setMode,
  } from '$lib/network.svelte'
  import type { Listed } from '$lib/network.svelte'

  /* No subscription here: the root layout follows Bluetooth and the
     radio for the whole session, so this screen only reads what is
     already there. The one fetch covers arriving before anything
     happened to be published. */
  $effect(() => {
    refreshNetwork()
  })

  const net = $derived(mode())
  const nearby = $derived(networks())
  const inRange = $derived(nearby.filter((ap) => ap.in_range).length)

  /* The network being joined for the first time, waiting on a
     password. Null the rest of the time. */
  let joining = $state<Listed | null>(null)
  let password = $state('')

  /* The code that joins the car's own network. Only offered while
     the hotspot is up -- there is nothing to scan otherwise. */
  let showingQr = $state(false)

  $effect(() => {
    password = joining ? '' : ''
  })

  /* Saved and open networks join straight away -- the daemon tries
     the stored profile first, which is what makes reconnecting work
     without being asked again. Only a secured network nobody has
     joined before needs the keyboard. */
  function tap(ap: Listed): void {
    if (ap.in_use) {
      leaveWifi()
    } else if (ap.saved || !secured(ap)) {
      join(ap.ssid)
    } else {
      joining = ap
    }
  }

  /** Signal as five steps, the same shape the radio scan uses. */
  const bars = (signal: number) =>
    Math.min(5, Math.max(1, Math.round(signal / 20)))

  /* What the hotspot or the connection is called, under the switch.
     Off says what it means on its own. */
  const netDetail = $derived(
    net === 'hotspot'
      ? network.state.hotspot.ssid
        ? `Serving ${network.state.hotspot.ssid}`
        : 'Serving a network'
      : network.state.wifi.connected
        ? `${network.state.wifi.ssid} · ${network.state.wifi.ip_address}`
        : 'Not connected to anything',
  )

  const on = $derived(bluetooth.state.adapter.service_active)
  const found = $derived(devices())
  const active = $derived(connected())

  /* What the line under the switch says. Whatever is connected is the
     only thing worth naming there; the adapter's own name belongs on
     the pairing screen, not here. */
  const summary = $derived(
    !on
      ? 'Off'
      : active
        ? `${active.name} · Connected`
        : found.some((device) => device.paired)
          ? 'No device connected'
          : 'No devices paired',
  )

  /* Paired but not connected is the common case -- a phone that has
     been in the car before. Never seen is the one that needs pairing,
     which only turns up while searching.
     
     Taken from the device rather than from what was asked for, so
     the word matches the spinner from the first frame: an unpaired
     device that is busy is pairing, whatever stage it has reached. */
  const action = (device: BtDevice, busy: boolean) => {
    if (device.connected) return busy ? 'Disconnecting' : 'Disconnect'
    if (device.paired) return busy ? 'Connecting' : 'Connect'
    return busy ? 'Pairing' : 'Pair'
  }

  /* Which device is being forgotten, or null. Confirmed rather than
     done on the tap: the bond is gone from both ends of the link, and
     the phone has to forget the car too before they can pair again --
     so a mis-tap while moving costs more than a moment. */
  let forgetting = $state<BtDevice | null>(null)

  function run(device: BtDevice): void {
    if (device.connected) disconnect(device.address)
    else if (device.paired) connect(device.address)
    else pair(device.address)
  }
</script>

<!-- One control, not two switches. Wi-Fi and the hotspot share the
     interface, so the car is on a network or serving one, never both
     and never neither -- two switches would let the screen ask for
     something that cannot happen. -->
<Card eyebrow="Network" gap="s">
  <!-- The control sits where a switch would, so the row reads the
       same way as every other setting: what it is on the left, what
       it is set to on the right. -->
  <Row title="Wi-Fi" detail={netDetail}>
    <!-- Before the control, not after it. The control is what the eye
         goes to and the finger reaches for, so it stays put: a button
         appearing to its right would shove it sideways every time the
         mode changed, under a finger already on its way. -->
    {#if net === 'hotspot'}
      <Button
        variant="quiet"
        square
        label="Show the code for joining"
        onclick={() => (showingQr = true)}
      >
        <Icon name="qrcode" size={22} />
      </Button>
    {/if}

    <Segmented
      label="Network mode"
      value={net}
      disabled={network.changing}
      options={[
        { value: 'wifi', label: 'Wi-Fi' },
        { value: 'hotspot', label: 'Hotspot' },
      ]}
      onchange={(next) => setMode(next as 'wifi' | 'hotspot')}
    />
  </Row>

  {#if net === 'wifi'}
    <div class="head">
      <span class="count">
        {#if network.scanning}
          Scanning
        {:else if inRange}
          {inRange} in range
        {:else if nearby.length}
          Saved networks
        {:else}
          Nothing yet
        {/if}
      </span>

      <Button
        variant="quiet"
        working={network.scanning}
        disabled={network.scanning || network.changing}
        onclick={() => scan()}
      >
        {#if network.scanning}
          <Spinner size={16} label="Scanning" />
        {:else}
          <Icon name="wifi" size={18} />
        {/if}
        Scan
      </Button>
    </div>

    {#if nearby.length}
      <ul class="networks">
        {#each nearby as ap (ap.ssid)}
          {@const busy = network.busy === ap.ssid}
          <li class="network" class:joined={ap.in_use}>
            <!-- Bars for something we heard, a mark for something we
                 only know about. A saved network out of range has no
                 signal to draw, and empty bars would read as a very
                 weak one. -->
            {#if ap.in_range}
              <span class="strength" aria-hidden="true">
                {#each [1, 2, 3, 4, 5] as step (step)}
                  <i
                    class:lit={step <= bars(ap.signal)}
                    style:height="{2 + step * 2}px"
                  ></i>
                {/each}
              </span>
            {:else}
              <span class="away" aria-hidden="true">
                <Icon name="wifi-off" size={16} />
              </span>
            {/if}

            <span class="ssid">{ap.ssid}</span>

            {#if secured(ap)}
              <Icon name="lock" size={16} />
            {/if}

            {#if !ap.in_range}
              <span class="badge">Not in range</span>
            {:else if ap.saved}
              <span class="badge">Saved</span>
            {/if}

            <Button
              variant={ap.in_use ? 'quiet' : 'primary'}
              working={busy}
              disabled={busy || !!network.busy || (!ap.in_range && !ap.in_use)}
              onclick={() => tap(ap)}
            >
              {#if busy}
                <Spinner size={16} label="Working" />
              {/if}
              {ap.in_use ? 'Disconnect' : ap.saved ? 'Connect' : 'Join'}
            </Button>

            {#if ap.saved}
              <Button
                variant="quiet"
                square
                label="Forget {ap.ssid}"
                disabled={!!network.busy}
                onclick={() => forgetWifi(ap.ssid)}
              >
                <Icon name="trash" size={20} />
              </Button>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  {/if}

  {#if network.changing}
    <p class="note">
      <Spinner size={16} label="Switching" />
      Switching takes a moment — services stop and start, and the car
      has to associate.
    </p>
  {:else if network.error}
    <p class="warning">{network.error}</p>
  {/if}
</Card>

<!-- The code and nothing else: a title would name what is already
     in front of you, and a Close button is one more thing to read
     when tapping anywhere outside does it. -->
<Dialog
  open={showingQr}
  bare
  title="Join {network.state.hotspot.ssid || 'the car'}"
  width={420}
  onclose={() => (showingQr = false)}
>
  <img class="qr" src={hotspotQr} alt="" />
</Dialog>

<Dialog
  open={!!joining}
  title="Join {joining?.ssid ?? ''}"
  width={560}
  onclose={() => (joining = null)}
>
  {#if joining}
    <div class="join">
      <KeyboardInput
        value={password}
        label="Password"
        placeholder="Network password"
        maxlength={63}
        onchange={(value) => (password = value)}
      />
      <p class="note">
        Saved once it connects, so the car joins on its own next time.
      </p>
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="quiet" onclick={() => (joining = null)}>Cancel</Button>
    <Button
      variant="primary"
      disabled={password.length < 8}
      onclick={() => {
        if (joining) join(joining.ssid, password)
        joining = null
      }}
    >
      Join
    </Button>
  {/snippet}
</Dialog>

<Card eyebrow="Bluetooth" gap="none" trim>
  <Row title="Bluetooth" detail={summary}>
    {#if bluetooth.switching}
      <Spinner size={22} label="Switching Bluetooth" />
    {/if}
    <Switch
      label="Bluetooth"
      checked={on}
      disabled={bluetooth.switching}
      onchange={(want) => setService(want)}
    />
  </Row>
</Card>

<Card eyebrow="Available devices" gap="s">
  <div class="head">
    <span class="count">
      {#if !on}
        Bluetooth is off
      {:else if searching()}
        Searching — {bluetooth.state.window.seconds_left}s
      {:else if found.length}
        {found.length} found
      {/if}
    </span>

    <Button
      variant="quiet"
      disabled={!on}
      onclick={() => toggleSearch()}
    >
      {#if searching()}
        <Spinner size={16} label="Searching" />
        Stop
      {:else}
        <Icon name="bluetooth" size={18} />
        Search
      {/if}
    </Button>
  </div>

  {#if on && found.length}
    <ul class="devices">
      {#each found as device (device.address)}
        {@const busy = busyWith(device.address)}
        <li class="device" class:connected={device.connected}>
          <!-- What the device is, not whether it is connected: the
               row already says that in its colour, and the kind is
               the thing you scan the list for. -->
          <Icon name={iconFor(device.icon)} size={24} />

          <span class="name">{device.name}</span>

          {#if device.paired}
            <span class="badge">Saved</span>
          {/if}

          {#if device.battery !== null}
            <span class="battery">{device.battery}%</span>
          {/if}

          <Button
            variant={device.connected ? 'quiet' : 'primary'}
            working={busy}
            disabled={busy}
            onclick={() => run(device)}
          >
            {#if busy}
              <Spinner size={16} label="Working" />
            {/if}
            {action(device, busy)}
          </Button>

          <!-- Only for devices there is something to forget about. A
               device merely seen nearby has no bond to remove. -->
          {#if device.paired}
            <Button
              variant="quiet"
              square
              label="Forget {device.name}"
              disabled={busy}
              onclick={() => (forgetting = device)}
            >
              <Icon name="trash" size={20} />
            </Button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if bluetooth.error}
    <p class="warning">{bluetooth.error}</p>
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
      Forget <strong>{forgetting.name}</strong>?
    </p>
    <p class="confirm detail">
      The car will not connect to it again until they are paired
      afresh — and the phone will need to forget the car on its side
      too, or it will refuse.
    </p>
  {/if}

  {#snippet footer()}
    <Button variant="quiet" onclick={() => (forgetting = null)}>
      Keep
    </Button>
    <Button
      variant="danger"
      onclick={() => {
        if (forgetting) forget(forgetting.address)
        forgetting = null
      }}
    >
      Forget
    </Button>
  {/snippet}
</Dialog>

<style>
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

  .devices {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .device {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    /* Tall enough to hit with a thumb, which is the whole reason a
       list row is not just text. */
    min-height: 62px;
    padding: 0 var(--spacing);
    color: var(--text-dim);
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .device.connected {
    color: var(--accent);
    border-color: var(--accent);
  }

  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  /* Said quietly: that a device is remembered matters less than what
     it is, and it is on most of the rows most of the time. */
  .badge {
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .battery {
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }

  .warning {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }

  /* On white whatever the theme: a scanner reads dark on light, and
     a code inverted by the night theme is one a phone will not
     see. */
  .qr {
    display: block;
    width: 100%;
    background: #fff;
    border-radius: var(--radius-sm);
  }

  .networks {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .network {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    min-height: 62px;
    padding: 0 var(--spacing);
    color: var(--text-dim);
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .network.joined {
    color: var(--accent);
    border-color: var(--accent);
  }

  .ssid {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  /* Bars rather than a percentage: nobody chooses a network by the
     number, only by which is stronger. */
  .strength {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 14px;
  }

  .strength i {
    width: 3px;
    background: var(--text-faint);
    border-radius: 1px;
  }

  .strength i.lit {
    background: var(--text);
  }

  /* Where the bars would be, so the names still line up. */
  .away {
    display: grid;
    place-items: center;
    width: 17px;
    color: var(--text-faint);
  }

  .join {
    display: flex;
    flex-direction: column;
    gap: var(--spacing);
    padding-bottom: var(--spacing-s);
  }

  .note {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    margin: 0;
    font-size: 13px;
    color: var(--text-dim);
  }

  .confirm {
    margin: 0 0 var(--spacing-s);
    font-size: 16px;
    color: var(--text-dim);
  }

  .confirm strong {
    color: var(--text);
  }

  .confirm.detail {
    margin-bottom: var(--spacing-l);
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-faint);
  }

</style>
