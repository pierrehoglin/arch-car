<script lang="ts">
  import Icon from './Icon.svelte'
  import logo from './assets/saab-logo.svg'
  import { NAV } from './types'

  interface Props {
    /** Current path, so the rail can mark where we are. */
    path: string
  }

  let { path }: Props = $props()

  /* Home is the only exact match. Every other section owns its
     subtree, so /media/radio should still light Media. */
  const active = (href: string) =>
    href === '/' ? path === '/' : path.startsWith(href)
</script>

<nav class="rail" aria-label="Main">
  <!-- Exactly as tall as the header, so the badge sits centred in the
       corner the two chrome edges make rather than floating near it. -->
  <div class="badge">
    <img src={logo} alt="Saab" />
  </div>

  <div class="items">
    {#each NAV as item (item.href)}
      <a
        class="item"
        class:active={active(item.href)}
        href={item.href}
        aria-current={active(item.href) ? 'page' : undefined}
      >
        <Icon name={item.icon} />
        <span class="label">{item.label}</span>
      </a>
    {/each}
  </div>

  <a
    class="item settings"
    class:active={active('/settings')}
    href="/settings"
    aria-current={active('/settings') ? 'page' : undefined}
  >
    <Icon name="settings" />
    <span class="label">Settings</span>
  </a>

  <div class="model">Saab 9-5</div>
</nav>

<style>
  .rail {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 120px;
    height: 100%;
    padding: 0 0 10px;
    background: var(--rail);
    border-right: 1px solid var(--hairline);
  }

  .badge {
    display: grid;
    place-items: center;
    width: 100%;
    height: 64px;
    flex-shrink: 0;
  }

  .badge img {
    width: 34px;
    height: 34px;
    border-radius: 50%;
  }

  .items {
    display: flex;
    flex-direction: column;
    width: 100%;
    margin-top: 6px;
  }

  .item {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    width: 100%;
    /* Deliberately tall. Every one of these is pressed with a thumb
       while moving, so they are sized for that rather than for the
       amount of content in them. */
    padding: 14px 0 12px;
    color: var(--text-dim);
    text-decoration: none;
    opacity: var(--dim-secondary);
    transition: color 120ms ease;
  }

  .item.active {
    color: var(--accent);
    opacity: 1;
  }

  /* The marker sits on the screen edge rather than inside the link,
     so the active item reads as attached to the rail. */
  .item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 3px;
    background: var(--accent);
  }

  .item:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -4px;
  }

  .label {
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .settings {
    margin-top: auto;
  }

  .model {
    margin-top: 10px;
    font-family: var(--font-display);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-faint);
    opacity: var(--dim-secondary);
  }

  @media (prefers-reduced-motion: reduce) {
    .item {
      transition: none;
    }
  }
</style>
