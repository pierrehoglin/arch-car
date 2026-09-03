<script lang="ts">
  import { page } from '$app/state'
  import type { Snippet } from 'svelte'
  import Segmented from '$lib/ui/Segmented.svelte'
  import { MEDIA_SOURCES } from '$lib/types'

  interface Props {
    children: Snippet
  }

  let { children }: Props = $props()

  const current = $derived(page.url.pathname)
</script>

<div class="media">
  <Segmented
    label="Source"
    options={MEDIA_SOURCES.map((source) => ({
      value: source.href,
      label: source.label,
      href: source.href,
    }))}
    value={current}
  />

  {@render children()}
</div>

<style>
  .media {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 18px;
    height: 100%;
    padding: var(--spacing-l) var(--spacing-xl) var(--spacing-xl);
    overflow-y: auto;
  }
</style>
