<script lang="ts">
  import Card from './Card.svelte'
  import { coverFor } from '../covers'
  import Player from './Player.svelte'
  import {
    command,
    elapsed,
    media,
    playerOf,
    refresh,
    seek,
    toggle,
    watch,
  } from '../media.svelte'

  /* One screen for every source.
   *
   * The Bluetooth and Spotify pages are this with different colours:
   * AVRCP and MPRIS carry the same things, so a screen that reads one
   * reads the other. Neither has a queue -- AVRCP browsing is a
   * separate profile BlueZ does not expose, and spotifyd implements
   * the MPRIS Player interface but not TrackList.
   */

  interface Props {
    /** bluetooth, spotify, or an MPRIS player name. */
    source: string
    /** Two colours standing in for artwork where there is none.
     *  Omitted for a source that never has any. */
    tint?: [string, string]
    /** Shown when nothing is playing. */
    empty: string
    /** And what to do about it. */
    hint: string
  }

  let { source, tint, empty, hint }: Props = $props()

  $effect(() => {
    refresh(source)
    return watch()
  })

  const player = $derived(playerOf(source))

  /* Present means there is a player; a title means it has something
     to say about a track. A phone connected with nothing started has
     the first and not the second. */
  const showing = $derived(player.present && !!player.title)

  /* Where the music is coming from, when that is somewhere else.
   *
   * A phone over Bluetooth is another device and worth naming. The
   * Spotify daemon is a process on this machine, and "via spotifyd"
   * under a tab already labelled Spotify says nothing the screen has
   * not said. */
  const elsewhere = $derived(
    source === 'bluetooth' ? player.device : '',
  )
</script>

{#if showing}
  <Player
    title={player.title}
    artist={player.artist}
    album={player.album}
    via={elsewhere}
    art={coverFor(player)}
    {tint}
    length={(player.duration ?? 0) / 1000}
    position={elapsed(source) / 1000}
    playing={player.status === 'playing'}
    onseek={player.seekable
      ? (seconds) => seek(source, Math.round(seconds * 1000))
      : undefined}
    onplay={() => toggle(source)}
    onprevious={() => command(source, 'prev')}
    onnext={() => command(source, 'next')}
  />
{:else}
  <Card gap="s" align="center" justify="center" class="nothing">
    <p class="what">{empty}</p>
    <p class="hint">{hint}</p>
    {#if player.device}
      <p class="via">Connected to {player.device}</p>
    {/if}
  </Card>
{/if}

{#if media.error}
  <p class="warning">{media.error}</p>
{/if}

<style>
  /* No spinner on the transport buttons: a command settles in well
     under the time one would be worth looking at, and the track
     changing is its own confirmation. */
  .what {
    margin: 0;
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
  }

  .hint {
    max-width: 44ch;
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    text-align: center;
    color: var(--text-dim);
  }

  .via {
    margin: var(--spacing-s) 0 0;
    font-size: 12.5px;
    color: var(--text-faint);
  }

  .warning {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }
</style>
