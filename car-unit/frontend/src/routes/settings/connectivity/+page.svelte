<script lang="ts">
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
</script>

<Card eyebrow="Connectivity" gap="none" trim>
  <Row title="Nothing here yet" detail="Coming in a later stage">
    <span class="pending">&mdash;</span>
  </Row>
</Card>

<style>
  .pending {
    color: var(--text-faint);
  }
</style>
