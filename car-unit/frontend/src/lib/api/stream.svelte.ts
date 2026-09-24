/* The daemon's event stream.
 *
 * One EventSource carrying named events, so a tune, an RDS decode or
 * the volume moving arrives when it happens rather than being
 * noticed on the next poll. Commands still go over POST -- this is
 * the direction that needed a channel.
 *
 * EventSource rather than a WebSocket: everything here goes one way,
 * it is plain HTTP through the same /api proxy, and it reconnects on
 * its own. That last point costs nothing in the car, where the
 * daemon runs until the ignition goes off, but it saves writing
 * reconnection logic for development.
 *
 * Opened once by the root layout and left open. Screens subscribe
 * and unsubscribe as they come and go; the connection outlives them.
 */

export type Handler = (data: unknown) => void

export type Connection = 'idle' | 'connecting' | 'open' | 'closed'

const PATH = '/api/events'

/* Every event the daemon sends. Listed rather than discovered,
   because EventSource only delivers a named event to a listener
   registered for that name -- so anything missing here is silently
   never received. */
const KNOWN = [
  'fm',
  'presets',
  'signals',
  'audio',
  'source',
  'bluetooth',
  'pairing',
  'media',
] as const

const handlers = new Map<string, Set<Handler>>()

/* The last payload of each kind.
 *
 * The daemon replays its current state to anyone connecting, but the
 * connection is opened at boot and screens subscribe later -- by
 * which time those frames are long delivered. Holding the last of
 * each means a screen mounting halfway through is populated at once
 * rather than waiting for something to change. */
const latest = new Map<string, unknown>()

let source: EventSource | undefined

/* The listeners attached to the current EventSource, so they can be
   taken off again. Closing the socket makes them unreachable anyway,
   but leaving them attached to an object we are about to drop means
   the teardown depends on the garbage collector rather than saying
   what it does. */
let attached: Array<[string, (message: MessageEvent) => void]> = []

/** Reported so a screen can say the readings are not live. */
export const stream = $state<{ connection: Connection }>({
  connection: 'idle',
})

/**
 * Listen for one kind of event.
 *
 * Called back immediately with the last payload of that kind, if one
 * has arrived. Returns an unsubscribe function, so an $effect can
 * hand it straight back.
 */
export function on(event: string, handler: Handler): () => void {
  let set = handlers.get(event)
  if (!set) {
    set = new Set()
    handlers.set(event, set)
  }
  set.add(handler)

  /* The replay is deferred, never called here.
   *
   * on() is called from inside $effect -- that is what a store's
   * watch() is for -- and a handler run synchronously would read
   * whatever state it touches as a dependency of that effect. Since
   * these handlers write that same state, the effect would re-run on
   * its own writes, for ever. A microtask is outside the effect, so
   * the reads there belong to nobody.
   *
   * Checked again on the way out: a screen can mount and unmount
   * inside one tick, and a handler that has unsubscribed must not
   * still be called.
   */
  if (latest.has(event)) {
    const held = latest.get(event)
    queueMicrotask(() => {
      if (set.has(handler)) handler(held)
    })
  }

  return () => {
    set.delete(handler)
    if (!set.size) handlers.delete(event)
  }
}

function receive(event: string, raw: string): void {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    /* Reported rather than swallowed. A frame that will not parse
       means the two ends disagree about encoding, and the symptom is
       a screen that never updates -- a long way from the cause. */
    console.warn(`stream: could not parse a "${event}" frame`, raw)
    return
  }

  latest.set(event, data)
  for (const handler of handlers.get(event) ?? []) handler(data)
}

/** Open the connection. Safe to call more than once. */
export function connect(): void {
  if (source) return

  stream.connection = 'connecting'
  source = new EventSource(PATH)

  /* Listeners for every known name, whether or not anything is
     subscribed yet. That is what fills the cache, and it is why a
     screen opened later does not have to wait.
     
     An event name missing from KNOWN is received by nobody:
     EventSource delivers a named event only to a listener registered
     for that name, and there is no error to notice. */
  attached = KNOWN.map((event) => {
    const listener = (message: MessageEvent) =>
      receive(event, message.data)
    source?.addEventListener(event, listener)
    return [event, listener] as [string, typeof listener]
  })

  source.onopen = () => {
    stream.connection = 'open'
  }

  source.onerror = () => {
    /* EventSource retries by itself, so this is not a failure to act
       on -- only something to show. CLOSED means it has given up,
       which it does only when the response was not a stream at all. */
    stream.connection =
      source?.readyState === EventSource.CLOSED ? 'closed' : 'connecting'
  }
}

export function disconnect(): void {
  for (const [event, listener] of attached) {
    source?.removeEventListener(event, listener)
  }
  attached = []

  source?.close()
  source = undefined

  /* The cache goes with the connection: what it holds describes a
     session that has ended, and replaying it to whoever subscribes
     next would hand them a reading from before the gap.
     
     Subscribers are left alone -- they are components, and they
     unsubscribe when they unmount. Clearing them here would leave a
     reconnect with nobody listening. */
  latest.clear()
  stream.connection = 'closed'
}
