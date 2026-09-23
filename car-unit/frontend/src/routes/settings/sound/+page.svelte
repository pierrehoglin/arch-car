<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Button from '$lib/ui/Button.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Slider from '$lib/ui/Slider.svelte'
  import {
    audio,
    nameOf,
    playing,
    refresh,
    setDefault,
    setDeviceMute,
    setDeviceVolume,
    setStreamMute,
    setStreamVolume,
    sinks,
    sources,
  } from '$lib/audio.svelte'
  import type { AudioDevice, AudioStream } from '$lib/api/types'

  /* The root layout follows audio for the whole session, so this
     screen only reads. The one fetch covers a screen opened before
     anything happened to be published. */
  $effect(() => {
    refresh()
  })

  const outputs = $derived(sinks())
  const inputs = $derived(sources())
  const apps = $derived(playing())

  /* PipeWire names carry the driver and the profile -- "CORSAIR
     VIRTUOSO XT Wireless Gaming Receiver Analog Stereo". The tail is
     much the same on everything and pushes the part that tells them
     apart off the end of the row. */
  function short(device: AudioDevice): string {
    return device.name
      .replace(/\s+(Analog|Digital)\s+(Stereo|Mono|Surround.*)$/i, '')
      .replace(/\s+Wireless\s+Gaming\s+Receiver/i, '')
      .trim()
  }

  const speaker = (device: { muted: boolean; percent: number | null }) =>
    device.muted
      ? 'muted'
      : !device.percent
        ? 'volume-zero'
        : device.percent <= 33
          ? 'volume-low'
          : device.percent <= 66
            ? 'volume-mid'
            : 'volume'
</script>

{#snippet devices(list: AudioDevice[], empty: string)}
  {#if list.length}
    {#each list as device (device.node_id)}
      <!-- No "in use" line: the tick and the accent already say it,
           and a label that appears on exactly one row makes the rows
           different heights for no gain. -->
      <Row
        title={short(device)}
        selected={device.is_default}
        onclick={() => setDefault(device.node_id)}
      >
        <div class="level">
          <Slider
            label="{short(device)} level"
            value={device.muted ? 0 : device.percent}
            readout="{device.muted ? 0 : device.percent}%"
            oninput={(percent) => setDeviceVolume(device.node_id, percent)}
          />
        </div>

        <Button
          variant="quiet"
          square
          pressed={device.muted}
          label="{device.muted ? 'Unmute' : 'Mute'} {short(device)}"
          onclick={() => setDeviceMute(device.node_id, !device.muted)}
        >
          <Icon name={speaker(device)} size={22} />
        </Button>
      </Row>
    {/each}
  {:else}
    <Row title={empty} />
  {/if}
{/snippet}

<Card eyebrow="Output" gap="none" trim>
  {@render devices(outputs, 'Nothing on the graph to play to')}
</Card>

<Card eyebrow="Input" gap="none" trim>
  {@render devices(inputs, 'No microphone on the graph')}
</Card>

<Card eyebrow="Playing now" gap="none" trim>
  {#if apps.length}
    {#each apps as stream (stream.id)}
      <!-- Levelled against each other rather than against the
           output: FM is broadcast-compressed and arrives far louder
           than anything streamed, and WirePlumber remembers the
           difference by application. -->
      <Row title={nameOf(stream)}>
        <div class="level">
          <Slider
            label="{nameOf(stream)} level"
            value={stream.muted ? 0 : (stream.percent ?? 0)}
            readout="{stream.muted ? 0 : (stream.percent ?? 0)}%"
            oninput={(percent) => setStreamVolume(stream.id, percent)}
          />
        </div>

        <Button
          variant="quiet"
          square
          pressed={stream.muted}
          label="{stream.muted ? 'Unmute' : 'Mute'} {nameOf(stream)}"
          onclick={() => setStreamMute(stream.id, !stream.muted)}
        >
          <Icon name={speaker(stream)} size={22} />
        </Button>
      </Row>
    {/each}
  {:else}
    <Row title="Nothing playing" />
  {/if}
</Card>

{#if audio.error}
  <p class="warning">{audio.error}</p>
{/if}

<style>
  .level {
    width: 260px;
  }

  .warning {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }
</style>
