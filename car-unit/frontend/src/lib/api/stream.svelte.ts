/* The daemon's event stream.
 *
 * One EventSource carrying named events, so a tune, an RDS decode or
 * a source change arrives when it happens rather than being noticed
 * on the next poll. Commands still go over POST -- this is the
 * direction that needed a channel.
 *
 * EventSource rather than a WebSocket: everything here goes one way,
 * it is plain HTTP through the same /api proxy, and it reconnects on
 * its own. That last point costs nothing in the car, where the daemon
 * runs until the ignition goes off, but it saves writing reconnection
 * logic for development, where carlibd restarts constantly.
 */

export type Handler = (data: unknown) => void

export type Connection = 'idle' | 'connecting' | 'open' | 'closed'

const PATH = '/api/events'

const handlers = new Map<string, Set<Handler>>()

let source: EventSource | undefined
let listeners = new Map<string, (event: MessageEvent) => void>()

/** Reported so a screen can say the readings are not live. */
export const stream = $state<{ connection: Connection }>({
  connection: 'idle',
})

/**
 * Listen for one kind of event.
 *
 * Returns an unsubscribe function, so an $effect can hand it back.
 */
export function on(event: string, handler: Handler): () => void {
  let set = handlers.get(event)
  if (!set) {
    set = new Set()
    handlers.set(event, set)
    attach(event)
  }
  set.add(handler)

  return () => {
    set.delete(handler)
    if (!set.size) {
      handlers.delete(event)
      detach(event)
    }
  }
}

function attach(event: string): void {
  if (!source || listeners.has(event)) return

  const listener = (message: MessageEvent) => {
    let data: unknown
    try {
      data = JSON.parse(message.data)
    } catch {
      // A frame that is not JSON is not ours to interpret.
      return
    }
    for (const handler of handlers.get(event) ?? []) handler(data)
  }

  listeners.set(event, listener)
  source.addEventListener(event, listener)
}

function detach(event: string): void {
  const listener = listeners.get(event)
  if (source && listener) source.removeEventListener(event, listener)
  listeners.delete(event)
}

/** Open the connection. Safe to call more than once. */
export function connect(): void {
  if (source) return

  stream.connection = 'connecting'
  source = new EventSource(PATH)

  source.onopen = () => {
    stream.connection = 'open'
  }

  source.onerror = () => {
    /* EventSource retries by itself, so this is not a failure to act
       on -- only something to show. It closes for good only when
       readyState reaches CLOSED. */
    stream.connection =
      source?.readyState === EventSource.CLOSED ? 'closed' : 'connecting'
  }

  // Anything already subscribed before the connection existed.
  for (const event of handlers.keys()) attach(event)
}

export function disconnect(): void {
  for (const event of [...listeners.keys()]) detach(event)
  source?.close()
  source = undefined
  stream.connection = 'closed'
}
