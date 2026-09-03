<script lang="ts">
  import Player from '$lib/ui/Player.svelte'

  /* Placeholder throughout. Nothing is wired to the daemon.
   *
   * Playback here starts from the phone -- spotifyd is a Connect
   * endpoint, so the car is a speaker the app picks rather than
   * something that browses a library. That is why there is no search
   * or playlist view: choosing what plays happens on the phone. */

  let playing = $state(true)
  let position = $state(74)

  const track = {
    title: 'Kärleken Väntar',
    artist: 'Kent',
    album: 'Vapen & Ammunition',
    via: 'Spotify Connect',
    length: 268,
  }

  /* Connect does report the queue, unlike Bluetooth on some phones. */
  const queue = [
    { title: 'Dom Andra — Kent', length: '4:12' },
    { title: 'Sundets Pärla — Kent', length: '3:38' },
    { title: 'FF — Kent', length: '4:02' },
  ]
</script>

<Player
  title={track.title}
  artist={track.artist}
  album={track.album}
  via={track.via}
  length={track.length}
  tint={['#1db954', '#0f6b33']}
  {position}
  {playing}
  {queue}
  onplay={(v) => (playing = v)}
  onseek={(v) => (position = v)}
/>
