<script lang="ts">
  /* Inline SVG rather than an icon font: these are stroked outlines at
     24px, and a font would need loading before the rail could render.

     A few are filled instead -- transport controls read better solid
     at the size they are used. */

  interface Props {
    name: string
    size?: number
  }

  let { name, size = 24 }: Props = $props()

  const stroked: Record<string, string> = {
    home: 'M3 10.2 12 3l9 7.2V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1v-9.8Z',
    media: 'M9 18V5l10-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm10-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
    map: 'M9 3 3 5.5v15L9 18l6 2.5 6-2.5v-15L15 6 9 3Zm0 0v15m6-12v14.5',
    phone: 'M6.6 3h-3A1.6 1.6 0 0 0 2 4.6C2 13.1 8.9 20 17.4 20a1.6 1.6 0 0 0 1.6-1.6v-3l-4-1.4-2 2.4a13.5 13.5 0 0 1-6-6l2.4-2L6.6 3Z',
    car: 'M4 16v2.5a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5V11l2-5.5A1 1 0 0 1 5 5h14a1 1 0 0 1 .9.6L22 11v7.5a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5V16M2 11h20M6 13.5h2m8 0h2',
    camera: 'M3 8.5A1.5 1.5 0 0 1 4.5 7h2.2l1.2-2h8.2l1.2 2h2.2A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-9Zm9 8.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z',
    settings: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Zm8.4-1.6.1-1.6-.1-1.6 2-1.6-2-3.4-2.4.9a7.9 7.9 0 0 0-2.8-1.6L14.8 2H9.2l-.4 2.7a7.9 7.9 0 0 0-2.8 1.6l-2.4-1-2 3.5 2 1.6-.1 1.6.1 1.6-2 1.6 2 3.4 2.4-.9a7.9 7.9 0 0 0 2.8 1.6l.4 2.7h5.6l.4-2.7a7.9 7.9 0 0 0 2.8-1.6l2.4.9 2-3.4-2-1.6Z',
    power: 'M12 3v9m5.7-6.7a8 8 0 1 1-11.4 0',
    volume: 'M11 5 6.5 9H3v6h3.5L11 19V5Zm3.5 3.5a5 5 0 0 1 0 7m2.8-9.8a9 9 0 0 1 0 12.6',
    cloud: 'M6.5 19a4.5 4.5 0 0 1-.5-9 6 6 0 0 1 11.6 1.5A3.8 3.8 0 0 1 17.5 19h-11Z',
    search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 5 5',
    plus: 'M12 5v14M5 12h14',
    minus: 'M5 12h14',
    compass: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm3.5-12.5-2 5.5-5.5 2 2-5.5 5.5-2Z',
    crosshair: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-5a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM12 2v3m0 14v3M2 12h3m14 0h3',
    check: 'm5 13 4 4L19 7',
  }

  /* Solid shapes. Transport controls at 24px read as smudges when
     stroked, and a play triangle in outline is genuinely ambiguous. */
  const filled: Record<string, string> = {
    play: 'M8 5.1v13.8a1 1 0 0 0 1.5.9l11-6.9a1 1 0 0 0 0-1.7l-11-7A1 1 0 0 0 8 5.1Z',
    pause: 'M7 4.5h3.2v15H7v-15Zm6.8 0H17v15h-3.2v-15Z',
    previous: 'M7 5.5a1 1 0 0 1 2 0v5.2l8.5-5.6a1 1 0 0 1 1.5.9v11.9a1 1 0 0 1-1.5.9L9 13.3v5.2a1 1 0 0 1-2 0v-13Z',
    next: 'M17 5.5a1 1 0 0 0-2 0v5.2L6.5 5.1A1 1 0 0 0 5 6v11.9a1 1 0 0 0 1.5.9l8.5-5.5v5.2a1 1 0 0 0 2 0v-13Z',
    heading: 'M12 3.2 4.6 20a.7.7 0 0 0 1 .9l6.4-3.4 6.4 3.4a.7.7 0 0 0 1-.9L12 3.2Z',
    note: 'M9 18V5.5l10-2V16M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm10-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  }

  const solid = $derived(name in filled)
  const path = $derived(filled[name] ?? stroked[name] ?? '')
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill={solid ? 'currentColor' : 'none'}
  stroke={solid ? 'none' : 'currentColor'}
  stroke-width="1.6"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d={path} />
</svg>
