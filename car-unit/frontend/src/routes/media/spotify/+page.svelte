<script lang="ts">
  import Source from '$lib/ui/Source.svelte'
</script>

<Source
  source="spotify"
  tint={['#1db954', '#0f7a38']}
  empty="Nothing playing"
  hint="Pick the car in Spotify Connect and press play. Connect means
        the phone chooses what plays; the car only follows."
/>
