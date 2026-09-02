<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    /** Small uppercase heading above the first row. */
    eyebrow?: string
    children: Snippet
  }

  let { eyebrow = '', children }: Props = $props()
</script>

<section class="card">
  {#if eyebrow}
    <div class="eyebrow">{eyebrow}</div>
  {/if}
  {@render children()}
</section>

<style>
  .card {
    padding: 20px 24px 6px;
    background: var(--surface);
    border-radius: var(--radius);
  }

  .eyebrow {
    margin-bottom: 6px;
  }
</style>
