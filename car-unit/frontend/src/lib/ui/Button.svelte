<script lang="ts">
  import type { Snippet } from 'svelte'

  type Variant = 'plain' | 'primary' | 'quiet'

  interface Props {
    variant?: Variant
    /** Square, for a button that is only an icon. */
    square?: boolean
    /** Marks a toggle as on, and carries the accent while it is. */
    pressed?: boolean
    disabled?: boolean
    /** Needed when the content is an icon with no text. */
    label?: string
    onclick?: () => void
    class?: string
    children: Snippet
  }

  let {
    variant = 'plain',
    square = false,
    pressed,
    disabled = false,
    label = '',
    onclick,
    class: extra = '',
    children,
  }: Props = $props()
</script>

<button
  class="button {variant} {extra}"
  class:square
  class:pressed
  {disabled}
  aria-label={label || undefined}
  aria-pressed={pressed}
  {onclick}
>
  {@render children()}
</button>

<style>
  .button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-xs);
    /* Sized for a thumb in a moving car rather than for its text. */
    min-height: 46px;
    padding: 0 var(--spacing-l);
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .button.primary {
    color: var(--accent-ink);
    background: var(--accent);
  }

  .button.quiet {
    color: var(--text-dim);
    background: none;
    border-color: var(--border);
  }

  .button.square {
    width: 54px;
    min-width: 54px;
    padding: 0;
  }

  .button.pressed {
    color: var(--accent);
    border-color: var(--accent);
  }

  .button:active:not(:disabled) {
    filter: brightness(0.92);
  }

  .button:disabled {
    /* Dimmed rather than hidden: the button stays where the eye
       expects it, it just has nothing to act on yet. */
    opacity: 0.45;
    cursor: default;
  }

  .button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
