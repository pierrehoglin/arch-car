<script lang="ts">
  interface Props {
    name: string
    size?: number
    /** Filled with the accent, for the selected favourite. */
    active?: boolean
  }

  let { name, size = 44, active = false }: Props = $props()

  /* Two letters: the initials of the first two words, or the first
     two letters when there is only one word. "Anna Lind" gives AL,
     "Service" gives SE. */
  const initials = $derived.by(() => {
    const words = name.trim().split(/\s+/)
    const letters = words
      .slice(0, 2)
      .map((word) => word[0] ?? '')
      .join('')
    return (letters.length > 1 ? letters : name.slice(0, 2)).toUpperCase()
  })
</script>

<span
  class="avatar"
  class:active
  style:--size="{size}px"
  style:--type="{Math.round(size * 0.34)}px"
  aria-hidden="true"
>
  {initials}
</span>

<style>
  .avatar {
    display: grid;
    place-items: center;
    flex-shrink: 0;
    width: var(--size);
    height: var(--size);
    font-family: var(--font-display);
    font-size: var(--type);
    font-weight: 600;
    letter-spacing: 0.04em;
    color: var(--text);
    background: var(--panel-2);
    border-radius: 50%;
  }

  .avatar.active {
    color: var(--accent-ink);
    background: var(--accent);
  }
</style>
