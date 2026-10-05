<script lang="ts">
  import { untrack } from 'svelte'
  import Button from '$lib/ui/Button.svelte'
  import Card from '$lib/ui/Card.svelte'
  import Row from '$lib/ui/Row.svelte'
  import Segmented from '$lib/ui/Segmented.svelte'
  import Spinner from '$lib/ui/Spinner.svelte'
  import { formatBytes, type MapJob } from '$lib/api/map'
  import {
    DETAIL_NAMES,
    cancel,
    checkLatest,
    download,
    downloadLabels,
    estimate,
    mapData,
    refresh,
    updateAvailable,
    watch,
  } from '$lib/mapdata.svelte'

  /* Fetched and followed: the stream replays the last progress, but
     a screen opened before anything was published needs the status
     once. The newest build is looked up on opening too -- it is one
     small request, and "is there an update?" is the question this
     screen is opened to answer. */
  $effect(() => {
    refresh().then(() => untrack(() => checkLatest()))
    return watch()
  })

  const info = $derived(mapData.info)
  const job = $derived(info?.job ?? null)
  const busy = $derived(!!job && !['done', 'failed', 'cancelled'].includes(job.phase))

  /* The detail being looked at. Starts at what is installed, or the
     last choice, and is only sent anywhere when Download is pressed. */
  let chosen = $state<number | null>(null)
  const detail = $derived(chosen ?? info?.maxzoom ?? info?.maxzoom_setting ?? 15)

  /* Size for the level in view. Needs the tool and the internet, and
     takes a few seconds; asked again only when the level changes.

     Reads two settled values rather than `info`, which is replaced on
     every progress event -- depending on it would re-run the size
     check twice a second all through a download. */
  const toolReady = $derived(!!info?.tool.available)

  $effect(() => {
    const level = detail
    if (!toolReady) return
    untrack(() => estimate(level))
  })

  const date = (seconds: number | null) =>
    seconds ? new Date(seconds * 1000).toLocaleDateString('sv-SE') : ''

  const installedLine = $derived.by(() => {
    if (!info?.available) return 'Not downloaded'
    const parts = [
      info.build ? `Build ${info.build}` : 'Added by hand',
      info.maxzoom ? `${DETAIL_NAMES[info.maxzoom] ?? info.maxzoom} detail` : '',
      formatBytes(info.size_bytes),
    ]
    return parts.filter(Boolean).join(' · ')
  })

  const latestLine = $derived.by(() => {
    if (mapData.checking) return 'Checking…'
    if (!info?.latest) return 'Not checked — needs internet'
    if (updateAvailable(info)) return `${info.latest.build} — newer than yours`
    if (info.available && info.build === info.latest.build) {
      return `${info.latest.build} — you have it`
    }
    return info.latest.build
  })

  const sizeLine = $derived.by(() => {
    if (!info?.tool.available) return 'Needs the pmtiles tool'
    if (mapData.estimating) return 'Working out the size…'
    if (mapData.estimate?.maxzoom === detail) {
      return `About ${formatBytes(mapData.estimate.bytes)} for all of Sweden`
    }
    return 'Size unknown'
  })

  const labelsLine = $derived.by(() => {
    if (!info?.labels.available) {
      return 'Not downloaded — names come from the internet'
    }
    return `Installed ${date(info.labels.installed)} · ${formatBytes(info.labels.size_bytes)}`
  })

  const PHASES: Record<MapJob['phase'], string> = {
    starting: 'Starting',
    checking: 'Finding the newest map',
    downloading: 'Downloading',
    installing: 'Installing',
    done: 'Done',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }
</script>

{#snippet progress(kind: MapJob['kind'])}
  {#if job && job.kind === kind}
    {#if busy}
      <div class="job">
        <div class="job-head">
          <span>{PHASES[job.phase]}</span>
          <span class="job-detail">
            {#if job.phase === 'downloading'}
              {Math.round(job.percent)}%{job.detail ? ` · ${job.detail}` : ''}
            {:else if job.expected_bytes}
              {formatBytes(job.expected_bytes)}
            {/if}
          </span>
        </div>
        <div
          class="bar"
          class:indeterminate={job.phase !== 'downloading'}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={job.percent}
        >
          <i style:width="{job.phase === 'downloading' ? job.percent : 100}%"></i>
        </div>
        <div class="job-actions">
          <!-- The old map keeps working throughout: the new one is
               written beside it and only swapped in when complete. -->
          <span class="note">The current map works until this finishes.</span>
          <Button variant="quiet" onclick={() => cancel()}>Cancel</Button>
        </div>
      </div>
    {:else if job.phase === 'failed'}
      <p class="warning">Download failed: {job.error}</p>
    {:else if job.phase === 'done'}
      <p class="note">
        Downloaded {date(job.finished)}. The map screen uses it the next
        time it opens.
      </p>
    {/if}
  {/if}
{/snippet}

<Card eyebrow="Offline map" gap="none" trim>
  <Row title="Map of Sweden" detail={installedLine}>
    {#if updateAvailable(info)}
      <span class="badge">Update available</span>
    {/if}
  </Row>

  <Row title="Newest map" detail={latestLine}>
    <Button
      variant="quiet"
      working={mapData.checking}
      disabled={mapData.checking}
      onclick={() => checkLatest()}
    >
      {#if mapData.checking}
        <Spinner size={16} label="Checking" />
      {/if}
      Check
    </Button>
  </Row>

  <!-- Each step roughly doubles the size. Below Full, zooming right in
       loses small things -- house numbers, footpaths, building
       outlines -- but roads and names are all there. -->
  <Row title="Detail" detail={sizeLine}>
    {#if mapData.estimating}
      <Spinner size={18} label="Working out the size" />
    {/if}
    <Segmented
      label="Map detail"
      disabled={busy}
      value={String(detail)}
      options={(info?.detail_levels ?? [12, 13, 14, 15]).map((level) => ({
        value: String(level),
        label: DETAIL_NAMES[level] ?? String(level),
      }))}
      onchange={(value) => (chosen = Number(value))}
    />
  </Row>

  <Row
    title={info?.available ? 'Update the map' : 'Download the map'}
    detail="Downloads in the background over the car's connection"
  >
    <Button
      variant="primary"
      disabled={busy || !info?.tool.available}
      onclick={() => download(detail)}
    >
      {info?.available ? 'Update' : 'Download'}
    </Button>
  </Row>

  {@render progress('tiles')}

  {#if info && !info.tool.available}
    <p class="warning">{info.tool.hint}</p>
  {/if}
</Card>

<Card eyebrow="Labels" gap="none" trim>
  <!-- Separate from the map: a few megabytes rather than gigabytes,
       and they change rarely. Without them the map draws with no
       names on it once the car is out of signal. -->
  <Row title="Fonts and icons" detail={labelsLine}>
    <Button
      variant={info?.labels.available ? 'quiet' : 'primary'}
      disabled={busy}
      onclick={() => downloadLabels()}
    >
      {info?.labels.available ? 'Update' : 'Download'}
    </Button>
  </Row>

  {@render progress('labels')}
</Card>

{#if mapData.error}
  <p class="warning">{mapData.error}</p>
{/if}

<style>
  .badge {
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--accent);
    white-space: nowrap;
  }

  .job {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    padding: var(--spacing) 0;
  }

  .job-head {
    display: flex;
    justify-content: space-between;
    gap: var(--spacing);
    font-size: 14px;
    font-weight: 600;
  }

  .job-detail {
    font-weight: 400;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .bar {
    height: 6px;
    overflow: hidden;
    background: var(--chip);
    border-radius: 3px;
  }

  .bar i {
    display: block;
    height: 100%;
    background: var(--accent);
    border-radius: 3px;
    transition: width 0.4s ease;
  }

  /* Checking and installing have no percentage. A slow pulse says
     something is happening without pretending to measure it. */
  .bar.indeterminate i {
    animation: pulse 1.4s ease-in-out infinite;
  }

  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }

  .job-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
  }

  .note {
    margin: 0;
    padding: var(--spacing-xs) 0;
    font-size: 13px;
    color: var(--text-dim);
  }

  .warning {
    margin: 0;
    padding: var(--spacing-xs) 0;
    font-size: 13px;
    color: var(--danger);
  }
</style>
