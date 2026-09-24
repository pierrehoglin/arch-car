import { sse } from 'msw'
import * as device from './device'

/* The event stream, standing in for the daemon's.
 *
 * MSW's sse namespace rather than http with a ReadableStream. Both
 * appear in their docs, but the stream version has to cross the
 * Service Worker boundary as a serialised response, and MSW built
 * the sse API precisely because that does not work reliably. This
 * one manages the connection itself.
 *
 * Server-sent events rather than a WebSocket: everything here goes
 * one way. Commands are POSTs already, and what comes back -- a
 * tune, RDS decoding, the volume moving -- is the daemon telling us
 * something happened. EventSource also reconnects on its own, which
 * matters every time carlibd restarts during development.
 */

export const stream = sse('/api/events', ({ client, request }) => {
  const send = (event: string, data: unknown) => {
    client.send({ event, data })
  }

  /* Current state first, so a screen that connects mid-session is
     populated without also having to fetch. A stream that only
     carries changes leaves the first paint empty until something
     happens to change. */
  send('fm', device.state())
  send('presets', device.allPresets())
  send('signals', device.signals())
  send('audio', device.audioState())
  send('bluetooth', device.bluetoothState())
  send('pairing', device.btPending())
  send('media', device.mediaNow('bluetooth'))
  send('media', device.mediaNow('spotify'))

  const unsubscribe = device.subscribe(send)

  /* The request is aborted when the EventSource is closed or the
     page goes away. Without unsubscribing, every reload would leave
     another listener writing to a client that has gone. */
  request.signal.addEventListener('abort', unsubscribe, { once: true })
})
