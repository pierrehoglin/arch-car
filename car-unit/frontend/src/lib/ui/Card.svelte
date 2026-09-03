<script lang="ts">
  import type { Snippet } from 'svelte'

  type Space = 'none' | 'xs' | 's' | 'm' | 'l' | 'xl'
  type Direction = 'column' | 'row'
  type Align = 'start' | 'center' | 'end' | 'stretch' | 'baseline'
  type Justify = 'start' | 'center' | 'end' | 'between' | 'around'

  interface Props {
    /** Small uppercase heading above the content. */
    eyebrow?: string
    /** Inner padding, from the spacing scale. */
    padding?: Space
    /** Space between children, and between the eyebrow and them. */
    gap?: Space

    /* The card is a flex container, so the properties every layout
       reaches for are props rather than something each page
       re-declares with :global. */
    direction?: Direction
    align?: Align
    justify?: Justify

    /** Renders as a link. For a card that is entirely one target. */
    href?: string
    /** Children carry their own trailing space -- Row does -- so the
     *  card gives up most of its bottom padding rather than doubling
     *  it. Without this a list of rows sits noticeably low. */
    trim?: boolean
    /** Anything the card should not know about: filling a column, a
     *  min-height of zero for scrolling. */
    class?: string
    children: Snippet
  }

  let {
    eyebrow = '',
    padding = 'l',
    gap = 's',
    direction = 'column',
    align = 'stretch',
    justify = 'start',
    href = '',
    trim = false,
    class: extra = '',
    children,
  }: Props = $props()

  const spacing: Record<Space, string> = {
    none: '0',
    xs: 'var(--spacing-xs)',
    s: 'var(--spacing-s)',
    m: 'var(--spacing)',
    l: 'var(--spacing-l)',
    xl: 'var(--spacing-xl)',
  }

  /* Short names in, CSS keywords out. "between" reads better at the
     call site than "space-between", and start/end avoid the flex-
     prefixed spellings entirely. */
  const alignment: Record<Align, string> = {
    start: 'flex-start',
    center: 'center',
    end: 'flex-end',
    stretch: 'stretch',
    baseline: 'baseline',
  }

  const distribution: Record<Justify, string> = {
    start: 'flex-start',
    center: 'center',
    end: 'flex-end',
    between: 'space-between',
    around: 'space-around',
  }
</script>

{#snippet inner()}
  {#if eyebrow}
    <div class="eyebrow">{eyebrow}</div>
  {/if}
  {@render children()}
{/snippet}

{#if href}
  <a
    class="card {extra}"
    class:trim
    {href}
    style:--pad={spacing[padding]}
    style:--inner={spacing[gap]}
    style:--direction={direction}
    style:--align={alignment[align]}
    style:--justify={distribution[justify]}
  >
    {@render inner()}
  </a>
{:else}
  <section
    class="card {extra}"
    class:trim
    style:--pad={spacing[padding]}
    style:--inner={spacing[gap]}
    style:--direction={direction}
    style:--align={alignment[align]}
    style:--justify={distribution[justify]}
  >
    {@render inner()}
  </section>
{/if}

<style>
  .card {
    display: flex;
    flex-direction: var(--direction);
    align-items: var(--align);
    justify-content: var(--justify);
    gap: var(--inner);
    padding: var(--pad);
    color: inherit;
    text-decoration: none;
    background: var(--surface);
    border-radius: var(--radius);
  }

  .card.trim {
    padding-bottom: var(--spacing-xs);
  }

  a.card:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
</style>
