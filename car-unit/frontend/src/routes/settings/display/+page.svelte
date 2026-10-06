<script lang="ts">
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Segmented from '$lib/ui/Segmented.svelte'
  import Swatches from '$lib/ui/Swatches.svelte'
  import { display, setAmbient, setTheme } from '$lib/settings.svelte'
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
      onchange={(v: Theme) => setTheme(v)}
    />
  </Row>

  <Row title="Ambient lighting" detail="Cabin accent colour">
    <Swatches
      value={display.ambient}
      theme={display.theme}
      onchange={(v) => setAmbient(v)}
    />
  </Row>
</Card>
