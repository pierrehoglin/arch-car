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

/**
 * How far into the track, in milliseconds.
 *
 * Extrapolated while playing, taken as-is when paused. Reading the
 * tick is what makes this recompute -- without it the value would be
 * right only at the moment a reading arrived.
 */
export function elapsed(source: string): number {
  void clock.tick

  const player = playerOf(source)
  if (player.position === null) return 0

  const since =
    player.status === 'playing'
      ? Date.now() - (media.read[source] ?? Date.now())
      : 0

  const at = player.position + since
  /* Clamped to the track: a reading that arrives late, or a clock
     that drifts, would otherwise run the bar past the end and keep
     going. */
  return player.duration === null ? at : Math.min(at, player.duration)
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

function apply(playing: NowPlaying): void {
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
 */
export function watch(): () => void {
  const off = on('media', (data) => {
    apply(data as NowPlaying)
  })

  if (!ticking) {
    ticking = setInterval(() => {
      clock.tick += 1
    }, 1000)
  }

  return () => {
    off()
    clearInterval(ticking)
    ticking = undefined
  }
}
