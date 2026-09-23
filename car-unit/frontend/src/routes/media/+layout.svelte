<script lang="ts">
  import { goto } from '$app/navigation'
  import { page } from '$app/state'
  import { untrack } from 'svelte'
  import type { Snippet } from 'svelte'
  import Segmented from '$lib/ui/Segmented.svelte'
  import { MEDIA_SOURCES } from '$lib/types'
  import { started, watch } from '$lib/media.svelte'

  interface Props {
    children: Snippet
  }

  let { children }: Props = $props()

  const current = $derived(page.url.pathname)

  /* Watched here as well as on the screen itself, so a source
     starting is noticed while you are looking at another one. */
  $effect(() => watch())

  /* Follow whatever starts playing.
   *
   * Only on the moment it starts, never on the fact that it is
   * playing: press play on the phone and the car shows the phone,
   * but choosing FM by hand afterwards stays chosen.
   *
   * `at` is what this depends on, not the source name -- starting
   * the same source twice has to count as two events, or the second
   * would move nothing.
   */
  $effect(() => {
    void started.at

    untrack(() => {
      const href = MEDIA_SOURCES.find(
        (source) => source.id === started.source,
      )?.href

      if (href && href !== page.url.pathname) goto(href)
    })
  })
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

  <!-- The screen a source draws itself on.
       
       Two elements rather than one because centring and scrolling do
       not mix: `justify-content: center` on a scrolling box clips the
       top of anything too tall to fit, and there is no scrolling back
       to reach it. `margin: auto` on the inner box centres the same
       way and pushes the box down instead of cutting it off. -->
  <div class="stage">
    <div class="content">
      {@render children()}
    </div>
  </div>
</div>

<style>
  .media {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 18px;
    height: 100%;
    padding: var(--spacing-l) var(--spacing-xl) var(--spacing-xl);
    /* The tabs stay put; only what is below them scrolls. */
    overflow: hidden;
  }

  .stage {
    display: flex;
    flex: 1;
    /* Without this a flex child refuses to shrink below its content,
       and the box grows past the screen instead of scrolling. */
    min-height: 0;
    width: 100%;
    overflow-y: auto;
  }

  .content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 18px;
    width: 100%;
    margin: auto;
  }
</style>
