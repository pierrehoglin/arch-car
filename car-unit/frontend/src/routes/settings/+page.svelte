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
  <Card padding="s" gap="none" class="sections">
    <nav aria-label="Settings sections">
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
  </Card>

  <div class="panels">
    {#if section === 'Display'}
      <Card eyebrow="Display" gap="none" trim>
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

      <Card eyebrow="Screen" gap="none" trim>
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
      <Card eyebrow={section} gap="none" trim>
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
    gap: var(--spacing-l);
    height: 100%;
    padding: var(--spacing-l);
    overflow-y: auto;
  }

  /* align-self is how the card sits in the grid, not how it lays out
     its own children, so it stays here rather than becoming a prop.
     :global because the class lands on the Card's element. */
  .settings :global(.sections) {
    align-self: start;
  }

  nav {
    display: flex;
    flex-direction: column;
  }

  .section {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
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
    gap: var(--spacing-l);
    align-content: start;
  }

  .pending {
    color: var(--text-faint);
  }
</style>
