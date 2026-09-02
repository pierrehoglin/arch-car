<script lang="ts" generics="T extends string">
  interface Props {
    options: { value: T; label: string }[]
    value: T
    onchange: (value: T) => void
    label?: string
  }

  let { options, value, onchange, label = '' }: Props = $props()
</script>

<div class="segmented" role="group" aria-label={label}>
  {#each options as option (option.value)}
    <button
      class:selected={value === option.value}
      onclick={() => onchange(option.value)}
      aria-pressed={value === option.value}
    >
      {option.label}
    </button>
  {/each}
</div>

<style>
  .segmented {
    display: flex;
    padding: 3px;
    background: var(--chip);
    border: 1px solid var(--border);
    border-radius: 10px;
  }

  button {
    min-width: 78px;
    height: 38px;
    padding: 0 18px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 8px;
  }

  button.selected {
    color: var(--accent-ink);
    background: var(--accent);
  }

  button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
