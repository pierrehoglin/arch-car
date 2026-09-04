import { HttpResponse, http } from 'msw'
import * as device from './device'

/* The event stream, standing in for the daemon's.
 *
 * Server-sent events rather than a WebSocket: everything here goes
 * one way. Commands are POSTs already, and what comes back -- a tune,
 * RDS decoding, a source changing -- is the daemon telling us
 * something happened. EventSource also reconnects on its own, which
 * matters every time carlibd restarts during development.
 *
 * The daemon's side is a StreamingResponse over the async generators
 * it already has: source.supervise() and gps.watch() yield when
 * something changes, which is precisely the shape of an SSE feed.
 */

/** Named so the client can dispatch without inspecting the payload. */
const HEARTBEAT_MS = 15_000

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

export const stream = http.get('/api/events', () => {
  const encoder = new TextEncoder()

  const body = new ReadableStream({
    start(controller) {
      const send = (event: string, data: unknown) => {
        try {
          controller.enqueue(encoder.encode(frame(event, data)))
        } catch {
          // The client went away between the check and the write.
        }
      }

      /* Current state first, so a screen that connects mid-session is
         populated without also having to fetch. A stream that only
         carries changes leaves the first paint empty until something
         happens to change. */
      send('fm', device.state())
      send('presets', device.allPresets())
      send('signals', device.signals())

      const unsubscribe = device.subscribe(send)

      /* A comment line, which EventSource ignores. Without traffic a
         proxy is entitled to drop an idle connection, and the first
         anyone would know is a screen quietly going stale. */
      const beat = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(': keep-alive\n\n'))
        } catch {
          clearInterval(beat)
        }
      }, HEARTBEAT_MS)

      return () => {
        unsubscribe()
        clearInterval(beat)
      }
    },

    cancel() {
      // The client closed the connection.
    },
  })

  return new HttpResponse(body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  })
})
