<script lang="ts">
  import type { Snippet } from 'svelte'

  type Variant = 'plain' | 'primary' | 'quiet' | 'danger'

  interface Props {
    variant?: Variant
    /** Square, for a button that is only an icon. */
    square?: boolean
    /** Marks a toggle as on, and carries the accent while it is. */
    pressed?: boolean
    /** Something is in flight. Keeps it legible while disabled, for
     *  a button whose content is a spinner. */
    working?: boolean
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
    working = false,
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
  class:working
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

  /* For the one action in a dialog that cannot be undone. A variant
     rather than a class passed in: styling a Button from outside
     needs :global, and a :global rule for a button in a footer
     snippet has no parent to scope it to. */
  .button.danger {
    color: #fff;
    background: var(--danger);
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

  /* Except while it is working. A button showing a spinner is doing
     something, and fading it to nearly half makes the one moving
     part on screen the hardest thing to see. */
  .button.working:disabled {
    opacity: 1;
  }

  .button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
