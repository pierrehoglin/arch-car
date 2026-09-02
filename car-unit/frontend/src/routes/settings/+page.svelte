<script lang="ts">
  import { goto } from '$app/navigation'
  import Icon from '$lib/Icon.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Segmented from '$lib/ui/Segmented.svelte'
  import Slider from '$lib/ui/Slider.svelte'
  import Swatches from '$lib/ui/Swatches.svelte'
  import { display } from '$lib/settings.svelte'
  import type { Theme } from '$lib/types'

  const sections = [
    'Display',
    'Sound',
    'Connectivity',
    'Vehicle',
    'Driver Assist',
    'About',
  ]

  let section = $state('Display')
</script>

<div class="settings">
  <nav class="sections" aria-label="Settings sections">
    {#each sections as name (name)}
      <button
        class="section"
        class:active={section === name}
        onclick={() => (section = name)}
        aria-current={section === name ? 'true' : undefined}
      >
        <span class="dot"></span>
        {name}
      </button>
    {/each}

    <button class="section close" onclick={() => goto('/')}>
      <Icon name="power" size={17} />
      Close
    </button>
  </nav>

  <div class="panels">
    {#if section === 'Display'}
      <Card eyebrow="Display">
        <Row title="Theme" detail="Light or dark instrument panel">
          <Segmented
            label="Theme"
            options={[
              { value: 'night', label: 'Dark' },
              { value: 'day', label: 'Light' },
            ]}
            value={display.theme}
            onchange={(v: Theme) => (display.theme = v)}
          />
        </Row>

        <Row title="Brightness">
          <Slider
            label="Brightness"
            readout="{display.brightness}%"
            value={display.brightness}
            onchange={(v) => (display.brightness = v)}
          />
        </Row>

        <Row title="Ambient lighting" detail="Cabin accent colour">
          <Swatches
            value={display.ambient}
            theme={display.theme}
            onchange={(v) => (display.ambient = v)}
          />
        </Row>
      </Card>

      <Card eyebrow="Screen">
        <Row title="Panel" detail="Waveshare 10.1 DSI touch">
          <Segmented
            label="Panel"
            options={[
              { value: 'on', label: 'On' },
              { value: 'off', label: 'Off' },
            ]}
            value={display.panel ? 'on' : 'off'}
            onchange={(v) => (display.panel = v === 'on')}
          />
        </Row>
      </Card>
    {:else}
      <Card eyebrow={section}>
        <Row title="Nothing here yet" detail="Coming in a later stage">
          <span class="pending">&mdash;</span>
        </Row>
      </Card>
    {/if}
  </div>
</div>

<style>
  .settings {
    display: grid;
    grid-template-columns: 208px 1fr;
    gap: 24px;
    height: 100%;
    padding: 24px;
    overflow-y: auto;
  }

  .sections {
    display: flex;
    flex-direction: column;
    align-self: start;
    padding: 14px;
    background: var(--surface);
    border-radius: var(--radius);
  }

  .section {
    display: flex;
    align-items: center;
    gap: 12px;
    height: 47px;
    padding: 0 14px;
    font-size: 15px;
    text-align: left;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: var(--radius-sm);
  }

  .section.active {
    color: var(--accent);
    background: var(--accent-soft);
  }

  .section:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  /* On every item so the labels line up whether or not one is
     selected, rather than shifting when the marker appears. */
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-faint);
  }

  .section.active .dot {
    background: var(--accent);
  }

  .close {
    margin-top: 10px;
    padding-top: 4px;
    border-top: 1px solid var(--hairline);
    border-radius: 0;
    color: var(--text);
  }

  .panels {
    display: flex;
    flex-direction: column;
    gap: 24px;
    align-content: start;
  }

  .pending {
    color: var(--text-faint);
  }
</style>
