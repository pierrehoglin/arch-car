<script lang="ts">
  import Keyboard from './Keyboard.svelte'

  /* A field that opens the on-screen keyboard when tapped.
   *
   * There is no hardware keyboard in the car, and the panel's Wayland
   * compositor has no zwp_input_method_manager_v2, so nothing appears
   * when a field is focused. This is the whole input path.
   *
   * The value only changes when the keyboard is done: what is typed
   * lives in the keyboard's own buffer until then, so cancelling
   * leaves the field as it was without anything to undo.
   *
   * The keyboard is rendered here rather than at the root, so it
   * cannot outlive the field it belongs to. Whatever removes the
   * field -- a dialog closing, a screen changing -- takes the
   * keyboard with it, and there is no state left behind to reappear
   * the next time.
   */

  interface Props {
    value: string
    label: string
    placeholder?: string
    maxlength?: number
    onchange: (value: string) => void
  }

  let {
    value,
    label,
    placeholder = '',
    maxlength = 24,
    onchange,
  }: Props = $props()

  let open = $state(false)
</script>

<div class="field">
  <span class="label">{label}</span>

  <!-- A button rather than an input: there is nothing to focus, and a
       real field would invite a caret that cannot be placed. -->
  <button class="value" class:empty={!value} onclick={() => (open = true)}>
    {value || placeholder || 'Tap to type'}
  </button>
</div>

{#if open}
  <!-- No target, so the keyboard renders its own buffer above the
       keys. That is the right shape here: the field this pairs with
       is a plain one on a screen, and the sheet usually covers it.
       
       A field that stays visible while typing -- the map's search --
       wants the other shape, and uses Keyboard directly with its own
       input as the target. -->
  <Keyboard
    initial={value}
    {label}
    {maxlength}
    ondone={(next) => {
      onchange(next)
      open = false
    }}
    oncancel={() => (open = false)}
  />
{/if}

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .label {
    font-family: var(--font-display);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-dim);
  }

  .value {
    display: flex;
    align-items: center;
    width: 100%;
    min-height: 54px;
    padding: 0 var(--spacing);
    font-family: var(--font-body);
    font-size: 18px;
    text-align: left;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .value.empty {
    color: var(--text-faint);
  }

  .value:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
</style>
