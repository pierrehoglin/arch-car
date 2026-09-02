<script lang="ts">
  /* Inline SVG rather than an icon font: these are stroked outlines at
     24px, and a font would need loading before the rail could render. */

  interface Props {
    name: string
    size?: number
  }

  let { name, size = 24 }: Props = $props()

  const paths: Record<string, string> = {
    home: 'M3 10.2 12 3l9 7.2V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1v-9.8Z',
    media: 'M9 18V5l10-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm10-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
    map: 'M9 3 3 5.5v15L9 18l6 2.5 6-2.5v-15L15 6 9 3Zm0 0v15m6-12v14.5',
    phone: 'M6.6 3h-3A1.6 1.6 0 0 0 2 4.6C2 13.1 8.9 20 17.4 20a1.6 1.6 0 0 0 1.6-1.6v-3l-4-1.4-2 2.4a13.5 13.5 0 0 1-6-6l2.4-2L6.6 3Z',
    car: 'M4 16v2.5a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5V11l2-5.5A1 1 0 0 1 5 5h14a1 1 0 0 1 .9.6L22 11v7.5a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5V16M2 11h20M6 13.5h2m8 0h2',
    camera: 'M3 8.5A1.5 1.5 0 0 1 4.5 7h2.2l1.2-2h8.2l1.2 2h2.2A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-9Zm9 8.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z',
    settings: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Zm8.4-1.6.1-1.6-.1-1.6 2-1.6-2-3.4-2.4.9a7.9 7.9 0 0 0-2.8-1.6L14.8 2H9.2l-.4 2.7a7.9 7.9 0 0 0-2.8 1.6l-2.4-1-2 3.5 2 1.6-.1 1.6.1 1.6-2 1.6 2 3.4 2.4-.9a7.9 7.9 0 0 0 2.8 1.6l.4 2.7h5.6l.4-2.7a7.9 7.9 0 0 0 2.8-1.6l2.4.9 2-3.4-2-1.6Z',
    power: 'M12 3v9m5.7-6.7a8 8 0 1 1-11.4 0',
    volume: 'M11 5 6.5 9H3v6h3.5L11 19V5Zm3.5 3.5a5 5 0 0 1 0 7m2.8-9.8a9 9 0 0 1 0 12.6',
  }
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.6"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d={paths[name] ?? ''} />
</svg>
