<script lang="ts">
  interface Props {
    checked: boolean
    onchange: (checked: boolean) => void
    label?: string
    /** While the change is being applied, so it cannot be flipped
     *  again before the first one has taken. */
    disabled?: boolean
  }

  let { checked, onchange, label = '', disabled = false }: Props = $props()
</script>

<button
  class="switch"
  class:on={checked}
  role="switch"
  aria-checked={checked}
  aria-label={label}
  {disabled}
  onclick={() => onchange(!checked)}
>
  <span class="knob"></span>
</button>

<style>
  .switch {
    position: relative;
    width: 62px;
    height: 34px;
    padding: 0;
    background: var(--chip);
    border: 1px solid var(--border);
    border-radius: 17px;
    transition: background 140ms ease;
  }

  .switch.on {
    background: var(--accent);
    border-color: transparent;
  }

  .knob {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 26px;
    height: 26px;
    background: var(--knob);
    border-radius: 50%;
    /* The one piece of motion here: it shows which way the switch
       moved, which a colour change alone does not. */
    transition: transform 140ms ease;
  }

  .switch.on .knob {
    transform: translateX(28px);
  }

  .switch:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .switch:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    .switch,
    .knob {
      transition: none;
    }
  }
</style>
