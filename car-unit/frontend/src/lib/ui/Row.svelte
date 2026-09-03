<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    title: string
    detail?: string
    /** The control on the right. */
    children: Snippet
  }

  let { title, detail = '', children }: Props = $props()
</script>

<div class="row">
  <div class="text">
    <div class="title">{title}</div>
    {#if detail}
      <div class="detail">{detail}</div>
    {/if}
  </div>

  <div class="control">
    {@render children()}
  </div>
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing-xl);
    /* Tall enough to hit while moving, and the hairline sits between
       rows rather than around them so the card reads as one object. */
    min-height: 78px;
    padding: 14px 0;
    border-bottom: 1px solid var(--hairline);
  }

  .row:last-child {
    border-bottom: 0;
  }

  .title {
    font-size: 16px;
    font-weight: 600;
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
</style>
