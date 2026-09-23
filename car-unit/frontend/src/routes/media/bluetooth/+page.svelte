<script lang="ts">
  import Source from '$lib/ui/Source.svelte'
</script>

<!-- Both media screens are the same screen. AVRCP and MPRIS carry the
     same things, so what differs is the source and how it looks.

     No tint: AVRCP never carries artwork, so a coloured square would
     be a placeholder for something that is never coming. -->
<Source
  source="bluetooth"
  empty="Nothing playing"
  hint="Start something on the phone. The car cannot begin playback
        on its own -- it only controls what the phone has started."
/>
