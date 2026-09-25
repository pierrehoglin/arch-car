import * as api from './api/media'
import { on } from './api/stream.svelte'
import { RequestFailed } from './api/client'
import type { Action } from './api/media'
import type { NowPlaying } from './api/types'

/* What each source is playing.
 *
 * One store for both, because AVRCP and MPRIS carry the same things:
 * the Bluetooth and Spotify screens differ only in which source they
 * read and how they look.
 *
 * Position is the interesting part. Neither transport signals it --
 * MPRIS says so explicitly, and AVRCP only reports on request -- so a
 * screen that waited to be told would show a frozen progress bar.
 * Instead the last reading is remembered with the moment it arrived,
 * and the elapsed time is worked out from there.
 */

const EMPTY: NowPlaying = {
  source: '',
  device: '',
  status: '',
  title: '',
  artist: '',
  album: '',
  duration: null,
  position: null,
  art: '',
  track_id: '',
  present: false,
}

interface Store {
  /** Keyed by source: bluetooth, spotify. */
  players: Record<string, NowPlaying>
  /** When each reading arrived, for working out the elapsed time. */
  read: Record<string, number>
  /** Sources with a command in flight. */
  busy: string[]
  error: string
}

export const media = $state<Store>({
  players: {},
  read: {},
  busy: [],
  error: '',
})

/* Ticks once a second so anything showing elapsed time re-renders.
   A single clock for every screen: a timer per progress bar would be
   the same work done several times, slightly out of step. */
const clock = $state({ tick: 0 })

let ticking: ReturnType<typeof setInterval> | undefined

export const playerOf = (source: string): NowPlaying =>
  media.players[source] ?? { ...EMPTY, source }

export const busyWith = (source: string) => media.busy.includes(source)

/* The sources the daemon polls, in the order to prefer them. The same
   order as the tabs, so the dashboard and the media screen agree
   about which one is "the" player when both have something. */
const SOURCES = ['spotify', 'bluetooth']

/**
 * The one worth showing on a screen that has room for one.
 *
 * Whatever is playing; failing that, whatever has a track, which is
 * the source you last listened to and would press play on again.
 * Null when neither has anything to say.
 */
export function current(): NowPlaying | null {
  const players = SOURCES.map(playerOf)

  return (
    players.find((player) => player.status === 'playing') ??
    players.find((player) => player.present && player.title) ??
    null
  )
}

/**
 * How far into the track, in milliseconds.
 *
 * Extrapolated while playing, taken as-is when paused. Reading the
 * tick is what makes this recompute -- without it the value would be
 * right only at the moment a reading arrived.
 */
export function elapsed(source: string): number {
  /* Reading the tick is what makes this recompute -- without it the
     value would be right only at the moment a reading arrived. */
  void clock.tick

  return at(playerOf(source), media.read[source] ?? Date.now())
}

/** Of the track, 0 to 1, for a progress bar. */
export function progress(source: string): number {
  const player = playerOf(source)
  if (!player.duration) return 0
  return Math.min(1, elapsed(source) / player.duration)
}

/** Milliseconds as m:ss. */
export function clockOf(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return '--:--'
  const total = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(total / 60)
  return `${minutes}:${String(total % 60).padStart(2, '0')}`
}

function report(cause: unknown): void {
  media.error =
    cause instanceof RequestFailed || cause instanceof Error
      ? cause.message
      : String(cause)
}

/** How far into the track a reading had got, by now. */
function at(player: NowPlaying, since: number): number {
  if (player.position === null) return 0

  const run =
    player.status === 'playing' ? Date.now() - (since || Date.now()) : 0

  const value = player.position + run
  return player.duration === null
    ? value
    : Math.min(value, player.duration)
}

/* The source that most recently started playing, and a counter that
   changes with it.
   
   A counter rather than just the name, because starting the same
   source twice is two events and a screen watching only the name
   would see no change the second time. */
export const started = $state<{ source: string; at: number }>({
  source: '',
  at: 0,
})

function apply(playing: NowPlaying): void {
  const was = media.players[playing.source]

  /* A transition into playing, not the fact of playing. Following
     the state would drag the screen back every time the reading
     arrived, so choosing a different source by hand would be
     impossible while anything was playing.
     
     `was` has to exist. Without that check the first reading of a
     source counts as a start -- so opening the media page while
     something is already playing fires one, and it then argues with
     whatever the page's own redirect had chosen. Arriving somewhere
     is not the same as something starting. */
  if (was && playing.status === 'playing' && was.status !== 'playing') {
    started.source = playing.source
    started.at = Date.now()
  }

  /* Taken as given. The daemon waits for the player to report a
     position for the state it has just moved to, so a reading is not
     published until it is one the screen can believe. */
  media.players = { ...media.players, [playing.source]: playing }
  media.read = { ...media.read, [playing.source]: Date.now() }
}

export async function refresh(source: string): Promise<void> {
  try {
    apply(await api.now(source))
    media.error = ''
  } catch (cause) {
    report(cause)
  }
}

/**
 * Send a command and apply what comes back.
 *
 * The response is the state after it took, so the screen settles
 * without waiting for the next poll -- which at two seconds is long
 * enough to press a button twice.
 */
export async function command(
  source: string,
  action: Action,
): Promise<void> {
  if (busyWith(source)) return

  media.busy = [...media.busy, source]
  try {
    apply(await api.command(source, action))
    media.error = ''
  } catch (cause) {
    report(cause)
  } finally {
    media.busy = media.busy.filter((held) => held !== source)
  }
}

/** Play if paused, pause if playing. */
export const toggle = (source: string) =>
  command(source, playerOf(source).status === 'playing' ? 'pause' : 'play')

/**
 * Follow the daemon.
 *
 * Subscribes only -- the connection belongs to the root layout. The
 * clock runs while anything is mounted and stops when nothing is,
 * so a parked car is not ticking for no one.
 *
 * Reference counted: the media layout watches so that a source
 * starting is noticed wherever you are, and the screen showing a
 * source watches too. The first to arrive starts the clock and the
 * last to leave stops it.
 */
let watchers = 0

export function watch(): () => void {
  const off = on('media', (data) => {
    apply(data as NowPlaying)
  })

  watchers += 1
  if (!ticking) {
    ticking = setInterval(() => {
      clock.tick += 1
    }, 1000)
  }

  return () => {
    off()
    watchers -= 1
    if (watchers === 0) {
      clearInterval(ticking)
      ticking = undefined
    }
  }
}
