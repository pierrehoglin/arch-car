<script lang="ts">
  import { page } from '$app/state'
  import type { Snippet } from 'svelte'
  import Icon from '$lib/Icon.svelte'
  import Card from '$lib/ui/Card.svelte'
  import { DEV_SECTIONS, SETTINGS_SECTIONS } from '$lib/types'

  interface Props {
    children: Snippet
  }

  let { children }: Props = $props()

  const path = $derived(page.url.pathname)

  const sections = import.meta.env.DEV
    ? [...SETTINGS_SECTIONS, ...DEV_SECTIONS]
    : SETTINGS_SECTIONS
</script>

<div class="settings">
  <Card padding="s" gap="none" class="sections">
    <nav aria-label="Settings sections">
      {#each sections as section (section.href)}
        <a
          class="section"
          class:active={path === section.href}
          href={section.href}
          aria-current={path === section.href ? 'page' : undefined}
        >
          <span class="dot"></span>
          {section.label}
        </a>
      {/each}

      <a class="section close" href="/">
        <Icon name="power" size={17} />
        Close
      </a>
    </nav>
  </Card>

  <div class="panels">
    {@render children()}
  </div>
</div>

<style>
  .settings {
    display: grid;
    grid-template-columns: 208px minmax(0, 1fr);
    /* One row, filling the screen. The scrolling happens inside the
       panels column, so the row has to be exactly as tall as the
       screen rather than as tall as its contents. */
    grid-template-rows: minmax(0, 1fr);
    gap: var(--spacing-l);
    height: 100%;
    padding: var(--spacing-l);
    overflow: hidden;
  }

  /* align-self is how the card sits in the grid, not how it lays out
     its own children, so it stays here rather than becoming a prop.
     :global because the class lands on the Card's element. */
  .settings :global(.sections) {
    align-self: start;
  }

  nav {
    display: flex;
    flex-direction: column;
  }

  .section {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    height: 47px;
    padding: 0 14px;
    font-size: 15px;
    text-align: left;
    color: var(--text-dim);
    text-decoration: none;
    border-radius: var(--radius-sm);
  }

  .section.active {
    color: var(--accent);
    background: var(--accent-soft);
  }

  .section:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  /* On every item so the labels line up whether or not one is
     selected, rather than shifting when the marker appears. */
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-faint);
  }

  .section.active .dot {
    background: var(--accent);
  }

  .close {
    margin-top: var(--spacing-s);
    padding-top: 4px;
    border-top: 1px solid var(--hairline);
    border-radius: 0;
    color: var(--text);
  }

  /* The only thing that scrolls. The sections stay put: a nav that
     slid away as you read a long panel would mean scrolling back up
     to change section.
     
     Padding on the right so a scrollbar sits beside the cards rather
     than over them, and a matching negative margin so the cards keep
     their place when there is none. */
  .panels {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-l);
    align-content: start;
    min-height: 0;
    overflow-y: auto;
    padding-right: var(--spacing-s);
    margin-right: calc(var(--spacing-s) * -1);
  }
</style>
