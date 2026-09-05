<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from '../Icon.svelte'

  /* The native <dialog>, so focus trapping, Escape and inertness of
     the page behind come from the browser rather than from us
     getting them nearly right. */

  interface Props {
    open: boolean
    title: string
    onclose: () => void
    /** Held open while something is running, so a scan cannot be
     *  dismissed halfway and leave the dongle busy. */
    dismissable?: boolean
    children: Snippet
    footer?: Snippet
  }

  let {
    open,
    title,
    onclose,
    dismissable = true,
    children,
    footer,
  }: Props = $props()

  let element = $state<HTMLDialogElement>()

  $effect(() => {
    if (!element) return
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  })
</script>

<dialog
  bind:this={element}
  aria-labelledby="dialog-title"
  onclose={onclose}
  oncancel={(e) => {
    // Escape, which the browser fires as cancel.
    if (!dismissable) e.preventDefault()
  }}
  onclick={(e) => {
    // The backdrop is part of the dialog element, so a click landing
    // on the element itself rather than its content is a click
    // outside the panel.
    if (dismissable && e.target === element) onclose()
  }}
>
  <!-- Unmounted when closed, not merely hidden. A native <dialog>
       only stops painting, so its children stay mounted with their
       state, their effects and their timers -- and anything they had
       opened is still open the next time it appears. -->
  {#if open}
    <div class="panel">
      <header>
        <h2 id="dialog-title">{title}</h2>

        <!-- Hidden while something is running, alongside the backdrop
             and Escape being disabled: all three are the same rule,
             and a close button that does nothing is worse than
             none. -->
        {#if dismissable}
          <button class="close" aria-label="Close" onclick={onclose}>
            <Icon name="close" size={22} />
          </button>
        {/if}
      </header>

      <div class="body">
        {@render children()}
      </div>

      {#if footer}
        <footer>
          {@render footer()}
        </footer>
      {/if}
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: 560px;
    width: calc(100vw - 96px);
    max-height: calc(100dvh - 120px);
    padding: 0;
    color: var(--text);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }

  dialog::backdrop {
    /* Dark rather than blurred: a blur costs a full-screen filter
       every frame, and this runs on a Pi. */
    background: rgb(0 0 0 / 0.6);
  }

  .panel {
    display: flex;
    flex-direction: column;
    max-height: calc(100dvh - 120px);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
    padding: var(--spacing-l) var(--spacing-l) var(--spacing-s);
  }

  .close {
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    /* Pulled toward the corner so the icon sits on the same optical
       margin as the title, rather than its box doing. */
    margin: -8px -10px -8px 0;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .close:active {
    background: var(--panel-2);
  }

  .close:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  h2 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0 var(--spacing-l);
  }

  footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--spacing-s);
    padding: var(--spacing-l);
  }
</style>
