# Bluetooth car-unit scripts — command reference

Installed as console scripts by `uv sync`. Run with `uv run`, or
activate the venv once and call them directly:

```bash
uv run bt-devices
```

`bt-call` and `bt-media` need `sudo` unless you add a D-Bus policy
(see [Reducing sudo](#reducing-sudo) below).

---

## bt-devices — paired device inventory

No subcommands. Lists everything BlueZ knows about, connected first.

| Command | What it does |
|---|---|
| `bt-devices` | Table: icon, name, MAC, state, RSSI, battery, now-playing |
| `bt-devices --json` | Same data as JSON |

Reads `org.bluez.Device1`, folds in `Battery1` percentage and the current
track from any `MediaPlayer1` under each device. Unpaired devices only
appear during an active scan.

---

## bt-call — calls over HFP (oFono)

Modem argument comes **after** the subcommand. Accepts a MAC in either
notation, an object path fragment, or a substring of the device name.

| Command | What it does |
|---|---|
| `modems` | List modems and their state — run this first to find what to pass |
| `online MODEM` | Power up and bring the modem online (populates `Interfaces`) |
| `dial MODEM NUMBER` | Place a call, then print state transitions until it ends |
| `dial MODEM NUMBER --hide-id` | Same, withholding caller ID |
| `answer MODEM` | Answer the incoming call |
| `hangup MODEM` | Hang up everything |
| `calls MODEM` | List active calls with state and caller |
| `monitor MODEM` | Watch `CallAdded`/`CallRemoved` signals live |
| `network MODEM` | Operator, registration status, signal strength, technology |
| `handsfree MODEM` | HFP features, phone battery level, in-band ringing |
| `volume MODEM --speaker 0-100 --mic 0-100 --mute on\|off` | Get or set call audio |
| `tones MODEM DIGITS` | Send DTMF during a call, e.g. `'1234#'` for phone menus |
| `voice MODEM [on\|off]` | Trigger the phone's own voice assistant; omit state to read |

**Setup reminder:** WirePlumber must defer HFP to oFono, and start order
matters — `bluetooth` → `ofono` → `wireplumber`. If `modems` shows an empty
`Interfaces` list, restart in that order.

---

## bt-media — playback over AVRCP (BlueZ)

Player argument comes after the subcommand, same matching rules.

| Command | What it does |
|---|---|
| `players` | List media players — run first to find what to pass |
| `status PLAYER` | Current status, title, artist, album, position/duration |
| `play` / `pause` / `stop PLAYER` | Direct transport control |
| `toggle PLAYER` | Play or pause depending on current state |
| `next` / `prev PLAYER` | Skip tracks |
| `forward` / `rewind PLAYER` | Seek |
| `monitor PLAYER` | Watch `PropertiesChanged` for track and status changes |
| `waybar PLAYER` | One JSON line with `text`, `class`, `tooltip` for a status bar |

The `MediaPlayer1` object only exists once the phone has an active media
session. If `players` is empty, start playback on the phone once.

---

## bt-phonebook — contacts and call logs over PBAP (obexd)

Address is the **first** argument here, options follow.

| Command | What it does |
|---|---|
| `bt-phonebook MAC` | Contacts from phone memory |
| `bt-phonebook MAC --book cch` | Combined call log, newest first, with direction glyphs |
| `bt-phonebook MAC --book ich` | Incoming calls only |
| `bt-phonebook MAC --book och` | Outgoing calls |
| `bt-phonebook MAC --book mch` | Missed calls |
| `bt-phonebook MAC --book fav` | Favourites |
| `bt-phonebook MAC --location sim1` | Read from SIM instead of phone memory |
| `bt-phonebook MAC --raw out.vcf` | Also keep the raw vCard data |
| `bt-phonebook MAC --json` | JSON output |

Needs contact sharing granted for this device in the phone's Bluetooth
settings. The table auto-detects call logs and switches format.

---

## bt-messages — SMS/MMS over MAP (obexd)

Address first, then subcommand.

| Command | What it does |
|---|---|
| `bt-messages MAC folders` | List message folders — start here to verify access |
| `bt-messages MAC list` | Inbox headers, unread marked with `*` |
| `bt-messages MAC list --folder sent` | Other folders: sent, outbox, draft, deleted |
| `bt-messages MAC list --count 50` | Fetch more (0 = no limit) |
| `bt-messages MAC list --json` | JSON output |
| `bt-messages MAC read HANDLE` | Full message body; handle comes from `list` |
| `bt-messages MAC read HANDLE --raw msg.bmsg` | Also keep the raw bMessage |

**Untested against your phone.** MAP support varies more than PBAP, and
Android needs a separate message-access permission per device. If
`folders` works, the rest should follow.

---

## dbus_explore.py — generic D-Bus exploration

| Command | What it does |
|---|---|
| `list-system` | Every well-known name on the system bus |
| `list-session` | Same for the session bus |
| `introspect SERVICE PATH` | Raw introspection XML for any object |
| `unit-state UNIT.service` | systemd unit state via D-Bus |
| `hostname` | hostname1 properties |

Useful when adding a new interface — introspect first, then write the
class to match the signatures you see.

---

# Suggested additions

Roughly in order of value for a car unit.

## 1. Unified daemon with a local API

The scripts each open their own bus connection and exit. A long-running
process holding one connection, subscribing to signals, and exposing a
small HTTP or Unix-socket API would let the UI react to events instead of
polling — incoming call, track change, device connect. This is the change
that turns a pile of scripts into a head unit.

FastAPI over a Unix socket, or just `aiohttp`. Keep the existing scripts
as thin clients so you can still debug from a terminal.

## 2. Incoming-call popup

`bt-call monitor` already sees `CallAdded` with the caller's number.
Cross-reference it against the PBAP contacts you can already fetch, and
show a notification with the name. `notify-send` works, or a layer-shell
window for something bigger and touch-friendly.

Caching the phonebook locally on connect makes the lookup instant.

## 3. Auto-connect and state recovery

Right now HFP needs a manual restart dance after boot. A systemd unit
ordered `After=bluetooth.service` with `Before=` on wireplumber, plus a
script that brings the modem online when a known phone connects, would
make the whole thing survive a reboot without intervention.

Watch `PropertiesChanged` on `Device1.Connected` to trigger it.

## 4. GPS / location

If you add a USB GPS dongle, `gpsd` exposes position over its own socket
(and there's a D-Bus interface too). Combined with the display you already
have, that's navigation-adjacent — or at minimum a speed readout.

## 5. OBD-II

A cheap ELM327 Bluetooth adapter pairs as a serial device and speaks a
simple text protocol over RFCOMM. `python-OBD` handles the parsing. Engine
temperature, RPM, fuel level, and fault codes on the panel is genuinely
the thing a car unit should do that a phone can't.

This pairs oddly with the single Bluetooth radio though — the Pi would be
connected to both the phone and the OBD adapter, which works but adds
contention. Worth testing before committing.

## 6. Reverse camera

The Pi 4's CSI connector is free (you're using DSI for the panel).
`libcamera` plus a trigger from a GPIO pin wired to the reverse light
would give you a camera view that appears automatically.

## 7. Audio routing polish

You have `snd_bcm2835.enable_headphones=0` in `cmdline.txt`, so onboard
audio is off. For a car unit you'd want either a USB DAC or to re-enable
it, plus WirePlumber rules that route HFP call audio and A2DP music to the
same output without manual switching.

## 8. Phonebook cache and search

PBAP fetches are slow — several seconds for a large phonebook. Cache to
SQLite on connect, then searching and reverse-lookup are instant. This is
a prerequisite for the incoming-call popup being useful.

## 9. Battery and power management

`vcgencmd get_throttled` catches undervoltage, which matters in a car
where supply is noisy. A safe-shutdown on ignition-off needs a supercap or
UPS HAT, but at minimum you could warn on the display.

---

# Reducing sudo

oFono's D-Bus policy is root-only by default. To run `bt-call`
unprivileged:

`/etc/dbus-1/system.d/ofono-user.conf`
```xml
<busconfig>
  <policy user="alarm">
    <allow send_destination="org.ofono"/>
  </policy>
</busconfig>
```

```bash
sudo systemctl reload dbus
```

BlueZ is more permissive — `bt-devices` and `bt-media` may already
work without sudo. Test before adding a policy you don't need.
