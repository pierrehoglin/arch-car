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
const KNOWN = ['fm', 'presets', 'signals', 'audio', 'source'] as const

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

  if (latest.has(event)) handler(latest.get(event))

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
     screen opened later does not have to wait. */
  for (const event of KNOWN) {
    source.addEventListener(event, (message: MessageEvent) =>
      receive(event, message.data),
    )
  }

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
  source?.close()
  source = undefined
  latest.clear()
  stream.connection = 'closed'
}
