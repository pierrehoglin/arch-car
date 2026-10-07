import * as api from './api/call'
import { on } from './api/stream.svelte'
import type { Call, CallPhone, CallStatus } from './api/call'

/* Phone calls, as every screen sees them.

   The daemon says what is going on through the 'call' event; this
   mirrors it, and adds what is the screens' own business: whether the
   card is open or tucked into the status bar, which request is under
   way, what the last one said went wrong, and a clock for durations.

   Started from the root layout, so a call that comes in on any screen
   is noticed -- the card and the indicator live there too. */

interface Store {
  status: CallStatus
  /** The card is showing, rather than only the indicator. */
  open: boolean
  /** The request under way, so its button can show it and not be
   *  pressed twice: 'answer', 'decline', 'hangup', 'hold', 'mute',
   *  'dial'. Empty when none. */
  busy: string
  /** What the last request said, until the next change. */
  error: string
  /** Unix seconds, ticking while a call is connected. */
  now: number
}

export const call = $state<Store>({
  status: { available: false, phones: [], calls: [] },
  open: false,
  busy: '',
  error: '',
  now: Date.now() / 1000,
})

/* Which call the card and the indicator are about, when there are
   several: the one that wants something done first. */
const RANK: Record<Call['state'], number> = {
  incoming: 0,
  waiting: 1,
  dialing: 2,
  alerting: 2,
  active: 3,
  held: 4,
  ended: 5,
}

/** Every call, the one that matters most first. */
export const calls = (): Call[] =>
  [...call.status.calls].sort((a, b) => RANK[a.state] - RANK[b.state])

/** The call the card leads with, or null when there is none. */
export const main = (): Call | null => calls()[0] ?? null

/** Calls not yet over. */
export const live = (): Call[] =>
  call.status.calls.filter((c) => c.state !== 'ended')

export const phoneOf = (c: Call): CallPhone | undefined =>
  call.status.phones.find((p) => p.address === c.phone)

/** "02:14", or "1:02:14" past the hour. */
export function duration(c: Call): string {
  if (!c.connected_at) return ''
  const total = Math.max(0, Math.floor(call.now - c.connected_at))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/* --- Following the daemon ------------------------------------------- */

let seen = new Set<string>()
let clock: ReturnType<typeof setInterval> | undefined
/** Called when a call ends, with its phone -- the phone screen
 *  refreshes that phone's recent calls. */
const endedListeners = new Set<(phone: string) => void>()

export function onEnded(listener: (phone: string) => void): () => void {
  endedListeners.add(listener)
  return () => endedListeners.delete(listener)
}

function take(next: CallStatus): void {
  const before = new Map(call.status.calls.map((c) => [c.id, c.state]))
  call.status = next
  call.error = ''

  for (const c of next.calls) {
    /* A call ringing that was not before opens the card, wherever it
       was left -- minimized for the last call is no reason to miss
       this one. A call placed from here opens it too. */
    if (!seen.has(c.id) && c.state !== 'ended') {
      call.open = true
    }
    if (c.state === 'ended' && before.get(c.id) && before.get(c.id) !== 'ended') {
      for (const listener of endedListeners) listener(c.phone)
    }
  }
  seen = new Set(next.calls.map((c) => c.id))

  /* Gone altogether once the last call has dropped out of the list:
     nothing to show, so nothing open. */
  if (!next.calls.length) call.open = false

  /* The clock only while something is counting. */
  const counting = next.calls.some((c) => c.connected_at && c.state !== 'ended')
  if (counting && !clock) {
    call.now = Date.now() / 1000
    clock = setInterval(() => (call.now = Date.now() / 1000), 1000)
  } else if (!counting && clock) {
    clearInterval(clock)
    clock = undefined
  }
}

/** Once, for the state before the next change. */
export async function refresh(): Promise<void> {
  try {
    take(await api.status())
  } catch {
    // Left to the stream.
  }
}

/** Follow the daemon. Returns the unsubscribe, for an $effect. */
export function watch(): () => void {
  return on('call', (data) => take(data as CallStatus))
}

/* --- Requests ---------------------------------------------------------- */

/** Run one request: busy while it is out, its error kept if it fails.
 *  Returns whether it worked. The state itself only ever changes from
 *  the event. */
async function run(what: string, action: () => Promise<unknown>): Promise<boolean> {
  if (call.busy) return false
  call.busy = what
  call.error = ''
  try {
    await action()
    return true
  } catch (cause) {
    call.error = api.failure(cause)
    return false
  } finally {
    call.busy = ''
  }
}

export const answer = (c: Call) => run('answer', () => api.answer(c.id))
export const decline = (c: Call) => run('decline', () => api.decline(c.id))
export const hangup = (c: Call) => run('hangup', () => api.hangup(c.id))
export const holdAnswer = (c: Call) => run('hold', () => api.holdAnswer(c.id))
export const toggleMute = (c: Call) =>
  run('mute', () => api.mute(!(phoneOf(c)?.muted ?? false), c.phone))

/** A keypad digit, sent at once. Not through run(): a second digit
 *  tapped while the first is on its way is meant, not a double press. */
export async function tone(c: Call, digit: string): Promise<void> {
  try {
    await api.tones(digit, c.id)
  } catch (cause) {
    call.error = api.failure(cause)
  }
}

/**
 * Place a call. Answers with the error to show where the call was
 * started from -- the keypad, a contact -- since before the call exists
 * there is no card to show it on; null when the phone took it.
 */
export async function dial(number: string, phone?: string): Promise<string | null> {
  if (call.busy) return null
  call.busy = 'dial'
  try {
    await api.dial(number, phone)
    call.open = true
    return null
  } catch (cause) {
    return api.failure(cause)
  } finally {
    call.busy = ''
  }
}

/** Whether a phone can place calls: one with a hands-free link. With
 *  an address, that phone in particular. */
export const canCall = (phone?: string): boolean =>
  phone
    ? call.status.phones.some((p) => p.address === phone.toUpperCase())
    : call.status.available

export const minimize = () => (call.open = false)
export const show = () => {
  if (call.status.calls.length) call.open = true
}
