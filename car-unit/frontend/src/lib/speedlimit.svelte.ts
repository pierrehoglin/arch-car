import { request } from './api/client'
import * as stored from './api/settings'
import { on } from './api/stream.svelte'

/* The speed limit where the car is, as the daemon has it -- from the
   route while navigating, from the road otherwise -- and whether the
   speed is over it.

   Kept here rather than in a screen so the map and the home tile show
   the same sign, and agree on when the warning is on. */

export interface SpeedLimit {
  /** Whether there is a sign at all. */
  shown: boolean
  /** km/h, or null for a limit not known: an empty sign. */
  limit: number | null
  source: 'route' | 'road' | null
}

export type WarnMode = 'off' | 'change' | 'always'

interface Store {
  current: SpeedLimit
  /** Counts changes to the limit, for the sign's pulse. */
  changes: number
  /** Inside the window after a change, for the "change" warning. */
  freshChange: boolean
  /** speedlimit.warn, speedlimit.warn_seconds, speedlimit.margin. */
  warn: WarnMode
  warnSeconds: number
  margin: number
}

export const speedLimit = $state<Store>({
  current: { shown: false, limit: null, source: null },
  changes: 0,
  freshChange: false,
  warn: 'change',
  warnSeconds: 10,
  margin: 5,
})

/** Whether anything has been heard yet. The first limit seen is where
 *  the car already is, not a change it has just driven past -- the
 *  screen opening is not news. */
let heard = false
let windowTimer: ReturnType<typeof setTimeout> | undefined

function take(next: SpeedLimit): void {
  const before = speedLimit.current.limit
  speedLimit.current = next
  if (!heard) {
    heard = true
    return
  }
  if (next.limit !== null && next.limit !== before) {
    speedLimit.changes++
    /* The warning window: open for the set time from this change,
       closed by a timer, so it ends on time even when nothing else
       moves -- the speed held steady, no new event. */
    speedLimit.freshChange = true
    clearTimeout(windowTimer)
    windowTimer = setTimeout(
      () => (speedLimit.freshChange = false),
      speedLimit.warnSeconds * 1000,
    )
  }
}

/** Once, for a screen opening before the next change. */
export async function refreshLimit(): Promise<void> {
  try {
    const now = await request<SpeedLimit>('/speedlimit')
    if (!heard) take(now)
  } catch {
    // Left to the stream.
  }
}

/** Follow the daemon. Returns the unsubscribe, for an $effect. */
export function watchLimit(): () => void {
  return on('speedlimit', (data) => take(data as SpeedLimit))
}

const MODES: WarnMode[] = ['off', 'change', 'always']

/** The warning settings, from the daemon. Each screen asks as it
 *  opens, so a change made in Settings is in force the next time. */
export async function loadLimitSettings(): Promise<void> {
  try {
    const all = await stored.all()
    for (const key of ['speedlimit.warn', 'speedlimit.warn_seconds', 'speedlimit.margin']) {
      const value = stored.valueAt(all, key)
      if (value !== undefined) applyLimitSetting(key, value)
    }
  } catch {
    // The defaults stand.
  }
}

/** A setting written from the Settings screen, in force at once. */
export function applyLimitSetting(key: string, value: unknown): void {
  if (key === 'speedlimit.warn' && MODES.includes(value as WarnMode)) {
    speedLimit.warn = value as WarnMode
  }
  if (key === 'speedlimit.warn_seconds' && Number(value) > 0) {
    speedLimit.warnSeconds = Number(value)
  }
  if (key === 'speedlimit.margin' && Number(value) >= 0) {
    speedLimit.margin = Number(value)
  }
}

/** Whether to show the speed in red: over the limit by more than the
 *  margin, and -- with the "change" setting -- only shortly after the
 *  limit changed. */
export function overLimit(kmh: number | null): boolean {
  const { limit, shown } = speedLimit.current
  if (!shown || limit === null || kmh === null) return false
  if (kmh <= limit + speedLimit.margin) return false
  if (speedLimit.warn === 'always') return true
  return speedLimit.warn === 'change' && speedLimit.freshChange
}
