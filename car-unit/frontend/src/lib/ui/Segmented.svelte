<script lang="ts" generics="T extends string">
  interface Option<V> {
    value: V
    label: string
    /** Renders this option as a link. For a segmented control whose
     *  choices are routes rather than local state. */
    href?: string
  }

  interface Props {
    options: Option<T>[]
    value: T
    /** Omit when the options carry hrefs -- navigation is the change. */
    onchange?: (value: T) => void
    label?: string
  }

  let { options, value, onchange, label = '' }: Props = $props()
</script>

<div class="segmented" role="group" aria-label={label}>
  {#each options as option (option.value)}
    {#if option.href}
      <a
        class:selected={value === option.value}
        href={option.href}
        aria-current={value === option.value ? 'page' : undefined}
      >
        {option.label}
      </a>
    {:else}
      <button
        class:selected={value === option.value}
        onclick={() => onchange?.(option.value)}
        aria-pressed={value === option.value}
      >
        {option.label}
      </button>
    {/if}
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

  button,
  a {
    display: grid;
    place-items: center;
    min-width: 78px;
    height: 38px;
    padding: 0 18px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-dim);
    text-decoration: none;
    background: none;
    border: 0;
    border-radius: 8px;
  }

  .selected {
    color: var(--accent-ink);
    background: var(--accent);
  }

  button:focus-visible,
  a:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
