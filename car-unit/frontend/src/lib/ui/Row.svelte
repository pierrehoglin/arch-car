<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from '../Icon.svelte'

  interface Props {
    title: string
    detail?: string

    /** Makes the whole row the control, for a list you pick from. */
    onclick?: () => void
    /** The chosen one in such a list. Shows a tick. */
    selected?: boolean
    disabled?: boolean

    /** The control on the right. Omitted for a row that is itself
     *  the control. */
    children?: Snippet
  }

  let {
    title,
    detail = '',
    onclick,
    selected = false,
    disabled = false,
    children,
  }: Props = $props()
</script>

<div class="row" class:selected>
  <!-- The text is the control, not the whole row. A row can also
       hold a slider, and a slider inside a button is a target within
       a target -- the drag would be swallowed by the click. -->
  <svelte:element
    this={onclick ? 'button' : 'div'}
    class="text"
    class:pick={!!onclick}
    type={onclick ? 'button' : undefined}
    disabled={onclick ? disabled : undefined}
    aria-pressed={onclick ? selected : undefined}
    {onclick}
  >
    {#if onclick}
      <!-- Space held whether or not it is ticked, so the titles do
           not shift as the choice moves down the list. -->
      <span class="tick" class:on={selected}>
        <Icon name="check" size={20} />
      </span>
    {/if}

    <span class="label">
      <span class="title">{title}</span>
      {#if detail}
        <span class="detail">{detail}</span>
      {/if}
    </span>
  </svelte:element>

  {#if children}
    <div class="control">
      {@render children()}
    </div>
  {/if}
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
    width: 100%;
    /* Tall enough to hit while moving, and the hairline sits between
       rows rather than around them so the card reads as one object. */
    min-height: 78px;
    padding: 14px 0;
    border-bottom: 1px solid var(--hairline);
  }

  .row:last-child {
    border-bottom: 0;
  }

  .text {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    min-width: 0;
    padding: 0;
    color: inherit;
    text-align: left;
    background: none;
    border: 0;
  }

  .text.pick {
    /* Reaches past the text so there is something to hit beside a
       short name, without running under the control. */
    flex: 1;
    align-self: stretch;
    border-radius: var(--radius-sm);
  }

  .text.pick:active {
    background: var(--panel-2);
  }

  .text.pick:disabled {
    opacity: 0.45;
  }

  .text.pick:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .label {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .row.selected .title {
    color: var(--accent);
  }

  .title {
    font-size: 16px;
    font-weight: 600;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .detail {
    margin-top: 3px;
    font-size: 12.5px;
    color: var(--text-dim);
    opacity: var(--dim-secondary);
  }

  .control {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-shrink: 0;
  }

  .tick {
    display: grid;
    place-items: center;
    width: 22px;
    color: var(--accent);
    visibility: hidden;
  }

  .tick.on {
    visibility: visible;
  }
</style>
