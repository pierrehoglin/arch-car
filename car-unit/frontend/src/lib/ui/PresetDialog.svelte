<script lang="ts">
  import Button from './Button.svelte'
  import Dialog from './Dialog.svelte'
  import KeyboardInput from './KeyboardInput.svelte'
  import { forgetPreset, savePreset } from '../radio.svelte'
  import type { Station } from '../api/types'

  interface Props {
    /** The preset being edited, or null when the dialog is closed. */
    preset: Station | null
    onclose: () => void
  }

  let { preset, onclose }: Props = $props()

  let name = $state('')
  let confirming = $state(false)

  /* Reset whenever a different preset is opened, so the field never
     shows the last one's name. */
  $effect(() => {
    name = preset?.name ?? ''
    confirming = false
  })

  const frequency = $derived(preset?.frequency ?? 0)
  const changed = $derived(name.trim() !== (preset?.name ?? ''))

  async function apply(): Promise<void> {
    if (!preset) return
    await savePreset(preset.frequency, name.trim())
    onclose()
  }

  async function remove(): Promise<void> {
    if (!preset) return
    await forgetPreset(preset.frequency)
    onclose()
  }
</script>

<Dialog open={!!preset} {onclose} title="Preset">
  <div class="body">
    <p class="frequency">{frequency.toFixed(1)} MHz</p>

    <KeyboardInput
      bind:value={name}
      label="Name"
      placeholder="{frequency.toFixed(1)} MHz"
      onchange={(v) => (name = v)}
      onsubmit={apply}
    />

    {#if confirming}
      <!-- Two steps, because deleting is the one action here that
           cannot be undone and the button sits next to Save. -->
      <div class="confirm">
        <p>Remove this preset? The station stays on the dial.</p>
        <div class="confirm-actions">
          <Button variant="quiet" onclick={() => (confirming = false)}>
            Keep
          </Button>
          <Button onclick={remove} class="danger">Remove</Button>
        </div>
      </div>
    {/if}
  </div>

  {#snippet footer()}
    {#if !confirming}
      <Button variant="quiet" onclick={() => (confirming = true)}>
        Remove
      </Button>
      <Button variant="primary" onclick={apply} disabled={!changed}>
        Save
      </Button>
    {/if}
  {/snippet}
</Dialog>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-l);
    padding-bottom: var(--spacing-s);
  }

  .frequency {
    margin: 0;
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .confirm {
    padding: var(--spacing);
    background: var(--panel-2);
    border-radius: var(--radius-sm);
  }

  .confirm p {
    margin: 0 0 var(--spacing);
    font-size: 14px;
    color: var(--text-dim);
  }

  .confirm-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--spacing-s);
  }

  .confirm-actions :global(.danger) {
    color: #fff;
    background: var(--danger);
  }
</style>
