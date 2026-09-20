<script lang="ts">
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Switch from '$lib/ui/Switch.svelte'
  import {
    allMocked,
    mocks,
    noneMocked,
    setAll,
    setGroup,
  } from '$lib/mocks/control.svelte'
  import { GROUPS } from '$lib/mocks/groups'

  const every = $derived(allMocked())
  const none = $derived(noneMocked())
</script>

<Card eyebrow="Mocks" gap="none" trim>
  <Row
    title="Mock everything"
    detail="Answer every API request in the browser instead of calling carlib"
  >
    <Switch
      label="Mock everything"
      checked={every}
      disabled={mocks.busy}
      onchange={(on) => setAll(on)}
    />
  </Row>
</Card>

<Card eyebrow="By area" gap="none" trim>
  {#each GROUPS as group (group.id)}
    <Row title={group.label} detail={group.detail}>
      <Switch
        label={group.label}
        checked={mocks.enabled[group.id]}
        disabled={mocks.busy}
        onchange={(on) => setGroup(group.id, on)}
      />
    </Row>
  {/each}
</Card>

<Card gap="s">
  <p class="note">
    {#if none}
      Everything goes to carlib on 127.0.0.1:8099. Anything the
      daemon does not serve yet will fail rather than fall back.
    {:else if every}
      Nothing reaches carlib. Switch off whichever areas the daemon
      already serves to work against the real thing.
    {:else}
      Mixed. What is switched off goes to carlib over the dev
      server's proxy, so the daemon must be running.
    {/if}
  </p>

  <!-- The one thing that cannot be mixed, and it is not obvious from
       a list of switches that look alike. -->
  <p class="note">
    Events is one connection carrying every kind of change, so it
    cannot be split. Mocked, nothing live pushes; live, nothing
    mocked does.
  </p>

  <p class="note">
    Takes effect at once, without a reload. Screens already loaded
    keep what they have until they next fetch — that data did come
    from wherever it came from.
  </p>
</Card>

<style>
  .note {
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-faint);
  }
</style>
