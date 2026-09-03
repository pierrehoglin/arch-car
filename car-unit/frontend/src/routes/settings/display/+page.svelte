<script lang="ts">
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Segmented from '$lib/ui/Segmented.svelte'
  import Slider from '$lib/ui/Slider.svelte'
  import Swatches from '$lib/ui/Swatches.svelte'
  import { display } from '$lib/settings.svelte'
  import type { Theme } from '$lib/types'
</script>

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
