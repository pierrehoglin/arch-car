# btlib

Bluetooth integration for the car unit. Library plus thin CLI tools.

The library is written for a future HTTP API: **nothing prints, nothing
exits, everything returns data**. The CLI files are presentation only, so
an API handler and a terminal command share the same call.

## Layout

| Module | Responsibility |
|---|---|
| `variants` | Unwrap `(signature, value)` tuples from sdbus |
| `errors` | Typed exceptions that map onto HTTP status codes |
| `bus` | Cached system/session bus connections |
| `match` | Select one device/modem/player from a loose identifier |
| `obex` | OBEX sessions and transfers, shared by PBAP and MAP |
| `bluez` | BlueZ interfaces: devices, battery, media players |
| `ofono` | oFono interfaces: modems, calls, handsfree, volume |
| `phonebook` | PBAP contacts and call logs, vCard parsing |
| `messages` | MAP messages, bMessage parsing |
| `media` | AVRCP playback control |
| `calls` | HFP call control |
| `cli` | Shared CLI plumbing — **not imported by the domain modules** |

Interfaces are grouped by the service that owns them, because that is how
they version. When BlueZ changes a signature you edit `bluez.py`; when
oFono does, `ofono.py`.

## Why not one class

sdbus binds each interface to a specific object path, so `MediaPlayer1`
and `VoiceCallManager` cannot be merged into one type without losing that
binding. More importantly, sdbus raises `ValueError` if an interface name
is declared twice in one process — which is exactly what happened when
`ObjectManager` and `Properties` were redeclared in the standalone
scripts. Declaring each interface once, in one place, makes that
impossible.

## CLI tools

```bash
./bt-devices                       # inventory with capabilities
./bt-call modems                   # then: online, dial, answer, monitor
./bt-media players                 # then: toggle, next, monitor, waybar
./bt-phonebook MAC --book cch      # contacts and call logs
./bt-messages MAC folders          # SMS over MAP
```

Every tool takes `--json`. Device selectors are optional where the
library can fall back to a single connected device.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Other error |
| 2 | Not found |
| 3 | Ambiguous match |
| 4 | Service not available |
| 5 | Transfer failed |
| 130 | Interrupted |

Useful in shell scripts: `bt-call modems >/dev/null || [ $? -eq 4 ] && ...`

## Using it from an API

The domain modules are already the API layer. A FastAPI handler is a
one-liner:

```python
from fastapi import FastAPI, HTTPException
from btlib import calls, media, errors

app = FastAPI()

@app.get('/media/status')
async def media_status(device: str | None = None):
    try:
        return (await media.status(device)).to_dict()
    except errors.NotFoundError as e:
        raise HTTPException(404, str(e))
    except errors.NotAvailableError as e:
        raise HTTPException(503, str(e))

@app.post('/calls/dial')
async def dial(number: str, device: str | None = None):
    return (await calls.dial(number, device)).to_dict()
```

The exception hierarchy exists for exactly this mapping:

| Exception | Status |
|---|---|
| `NotFoundError` | 404 |
| `AmbiguousMatchError` | 409 |
| `NotAvailableError` | 503 |
| `TransferError` | 502 |
| `BtError` | 500 |

### Streaming events

`calls.watch()` and `media.watch()` are async generators over D-Bus
signals — no polling. They map directly onto WebSocket or SSE:

```python
@app.websocket('/events/calls')
async def call_events(ws: WebSocket):
    await ws.accept()
    async for kind, call in calls.watch():
        await ws.send_json({'event': kind, 'call': call.to_dict()})
```

This is what an incoming-call popup should consume. Combine it with
`phonebook.index_by_number()` for caller ID:

```python
contacts = await phonebook.fetch(mac)
index = phonebook.index_by_number(contacts)

async for kind, call in calls.watch():
    name = phonebook.lookup_number(index, call.number)
```

Cache that index on connect — PBAP fetches take seconds, which is too
slow to do while the phone is ringing. The index keys on the last seven
digits, so `+46701234567`, `0701234567` and `070-123 45 67` all resolve.

## Buses

BlueZ and oFono are on the **system** bus; obexd is on the **session**
bus. A systemd system service will not have `DBUS_SESSION_BUS_ADDRESS`,
so anything using `phonebook` or `messages` must run as a user unit.

`bus.py` caches both connections, which matters for a daemon: signal
subscriptions die with their connection.

## Requirements

```bash
sudo pacman -S python-sdbus ofono bluez bluez-obex
sudo systemctl enable --now bluetooth ofono
systemctl --user enable --now obex
```

HFP additionally needs WirePlumber to defer to oFono and correct start
ordering — see `HFP_SERVICE_ORDERING.md`.

## Testing without hardware

The parsers and matcher are pure functions with no D-Bus dependency:

```python
from btlib.phonebook import parse_vcards, index_by_number
from btlib.messages import parse_bmessage, build_bmessage
from btlib.match import select
```

These are the parts most likely to break on an unfamiliar phone, and they
can be tested against captured `--raw` output.
