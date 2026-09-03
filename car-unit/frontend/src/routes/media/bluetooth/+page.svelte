<script lang="ts">
  import Player from '$lib/ui/Player.svelte'

  /* Placeholder throughout. Nothing is wired to the daemon. */

  let playing = $state(true)
  let position = $state(299)

  const track = {
    title: 'Redbone',
    artist: 'Childish Gambino',
    album: 'Awaken, My Love!',
    via: 'Fake Phone',
    length: 327,
  }

  /* Only some phones send this. A queue needs AVRCP browsing, which
     Android generally supports and iOS does not, so it will be empty
     for a good share of devices. */
  const queue = [
    { title: 'Harbour Lights — Ora Vale', length: '3:52' },
    { title: 'Northbound — Kite Season', length: '4:18' },
    { title: 'Slow Ferry — Halva Vägen', length: '2:59' },
  ]
</script>

<Player
  title={track.title}
  artist={track.artist}
  album={track.album}
  via={track.via}
  length={track.length}
  {position}
  {playing}
  {queue}
  onplay={(v) => (playing = v)}
  onseek={(v) => (position = v)}
/>
