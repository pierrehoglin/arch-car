<script lang="ts" generics="T extends string">
  import Icon from '../Icon.svelte'

  /* One choice from a list that is too long, or too changeable, to
     lay out as a segmented control: a button saying what is chosen,
     opening a list under it.

     Built rather than a native <select>. The browser draws its own
     popup for that, in its own type and at its own size, which on a
     car screen means small text and targets sized for a mouse. */

  interface Option<V> {
    value: V
    label: string
  }

  interface Props {
    options: Option<T>[]
    value: T
    onchange: (value: T) => void
    /** Spoken name for the control. */
    label: string
    disabled?: boolean
  }

  let { options, value, onchange, label, disabled = false }: Props = $props()

  let open = $state(false)
  let root = $state<HTMLDivElement>()

  const current = $derived(
    options.find((option) => option.value === value)?.label ?? '',
  )

  function pick(next: T): void {
    open = false
    if (next !== value) onchange(next)
  }

  /* Closed by a touch anywhere else, and by Escape -- which is kept
     from reaching the dialog around it, so it closes the list and not
     the whole dialog. Cancelled as well as stopped: a native <dialog>
     closes on Escape by itself, without a listener, unless the key
     press is cancelled. */
  $effect(() => {
    if (!open) return

    const outside = (event: PointerEvent) => {
      if (root && !root.contains(event.target as Node)) open = false
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      open = false
    }

    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('keydown', escape, true)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      document.removeEventListener('keydown', escape, true)
    }
  })

  /* Disabled while open -- a load starting -- closes it, rather than
     leaving a list whose choices do nothing. */
  $effect(() => {
    if (disabled) open = false
  })
</script>

<div class="dropdown" bind:this={root}>
  <button
    class="trigger"
    class:open
    {disabled}
    aria-haspopup="listbox"
    aria-expanded={open}
    aria-label="{label}: {current}"
    onclick={() => (open = !open)}
  >
    <span class="current">{current}</span>
    <span class="chevron">
      <Icon name="chevron-down" size={18} />
    </span>
  </button>

  {#if open}
    <ul class="list" role="listbox" aria-label={label}>
      <!-- By position: options are named by whoever made them, and
           nothing promises the labels are unique. -->
      {#each options as option, index (index)}
        <li>
          <button
            class="option"
            class:selected={option.value === value}
            role="option"
            aria-selected={option.value === value}
            onclick={() => pick(option.value)}
          >
            {option.label}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .dropdown {
    position: relative;
  }

  .trigger {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing-s);
    min-width: 180px;
    max-width: 260px;
    height: 46px;
    padding: 0 var(--spacing-s) 0 var(--spacing);
    font-family: var(--font-body);
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .trigger.open {
    border-color: var(--accent);
  }

  .trigger:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .trigger:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .current {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .chevron {
    display: grid;
    flex-shrink: 0;
    color: var(--text-dim);
    transition: transform 160ms ease;
  }

  .open .chevron {
    transform: rotate(180deg);
  }

  /* Under the button, right-aligned with it: the control sits at the
     right edge of whatever it is in, and a list running off that edge
     would be cut. At least as wide as the button. */
  .list {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    z-index: 10;
    min-width: 100%;
    max-height: 300px;
    margin: 0;
    padding: 4px;
    overflow-y: auto;
    list-style: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.35);
  }

  .option {
    display: block;
    width: 100%;
    min-height: 46px;
    padding: 0 var(--spacing);
    font-family: var(--font-body);
    font-size: 15px;
    text-align: left;
    white-space: nowrap;
    color: var(--text);
    background: none;
    border: 0;
    border-radius: calc(var(--radius-sm) - 2px);
  }

  .option:active {
    background: var(--panel-2);
  }

  .option.selected {
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-soft);
  }

  .option:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  @media (prefers-reduced-motion: reduce) {
    .chevron {
      transition: none;
    }
  }
</style>
