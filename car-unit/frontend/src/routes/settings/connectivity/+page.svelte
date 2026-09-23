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

  /* No subscription here: the root layout follows Bluetooth for the
     whole session, so this screen only reads what is already there. */

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
