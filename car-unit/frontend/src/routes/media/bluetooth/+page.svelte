<script lang="ts">
  import Source from '$lib/ui/Source.svelte'
</script>

<!-- Both media screens are the same screen. AVRCP and MPRIS carry the
     same things, so what differs is the source and the colours. -->
<Source
  source="bluetooth"
  tint={['#4a8fd4', '#6f7ad0']}
  empty="Nothing playing"
  hint="Start something on the phone. The car cannot begin playback
        on its own -- it only controls what the phone has started."
/>
