<script lang="ts">
  interface Props {
    size?: number
    /** Spoken while something is running. */
    label?: string
  }

  let { size = 34, label = 'Working' }: Props = $props()
</script>

<span
  class="spinner"
  style:--size="{size}px"
  style:--stroke="{Math.max(2, Math.round(size / 11))}px"
  role="status"
  aria-label={label}
></span>

<style>
  .spinner {
    display: block;
    width: var(--size);
    height: var(--size);
    border: var(--stroke) solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 900ms linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* Slowed rather than stopped: something still has to say the screen
     is busy, and a frozen ring says the opposite. */
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation-duration: 2.4s;
    }
  }
</style>
