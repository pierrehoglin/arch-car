# Restructure: btlib to carlib

CAN bus arriving changes the calculus. Previously every module talked
D-Bus, so flat was right. socketcan is a different transport with no
D-Bus involvement at all, which introduces a real second axis — and
`btlib` was already the wrong name for something holding GPS code.

## New structure

```
backend/
├── pyproject.toml
├── uv.lock
├── carlib/
│   ├── __init__.py
│   ├── core/                    transport-agnostic
│   │   ├── __init__.py
│   │   ├── errors.py            typed exceptions
│   │   ├── match.py             fuzzy device selection
│   │   └── output.py            CLI helpers (was cli.py)
│   ├── dbus/                    D-Bus plumbing + interfaces
│   │   ├── __init__.py
│   │   ├── connection.py        bus connections (was bus.py)
│   │   ├── variants.py          variant unwrapping
│   │   ├── bluez.py
│   │   ├── ofono.py
│   │   ├── obex.py
│   │   └── modemmanager.py
│   ├── bluetooth/               domain: via D-Bus
│   │   ├── __init__.py
│   │   ├── calls.py             media.py
│   │   └── phonebook.py         messages.py
│   ├── location/                domain: via D-Bus
│   │   ├── __init__.py
│   │   └── gps.py               (was location.py)
│   └── vehicle/                 domain: via socketcan
│       ├── __init__.py
│       └── can.py               NEW
└── cli/
    ├── __init__.py
    ├── bt_call.py    bt_media.py     bt_devices.py
    ├── bt_phonebook.py               bt_messages.py
    ├── gps.py
    └── can.py                        NEW
```

## Why these boundaries

**`core/` imports no transport.** Verified: importing `carlib.core` and
`carlib.vehicle.can` does not load sdbus. A CAN-only process carries no
D-Bus dependency, and that property is what makes the split worth the
longer import paths.

**`dbus/` holds every interface declaration.** sdbus raises `ValueError`
if an interface name is declared twice in one process — the error that
bit twice with `ObjectManager` and `Properties`. One declaration site
makes that impossible.

**Domain packages are grouped by subject, not transport.** When OBD-II
arrives it joins `vehicle/`; a reverse camera would be its own package.

## Renames

| Old | New |
|---|---|
| `btlib/bus.py` | `carlib/dbus/connection.py` |
| `btlib/cli.py` | `carlib/core/output.py` |
| `btlib/location.py` | `carlib/location/gps.py` |
| `BtError` | `CarError` (old name aliased, still works) |

## Import changes

```python
# before
from btlib import calls, media
from btlib.cli import run, emit_json
from btlib.errors import NotFoundError
from btlib import location

# after
from carlib.bluetooth import calls, media
from carlib.core.output import run, emit_json
from carlib.core.errors import NotFoundError
from carlib.location import gps
```

## Applying it

```bash
cd backend
rm -rf btlib cli
# copy carlib/ and cli/ from the download
cp -r /path/to/carlib .
cp -r /path/to/cli .
cp /path/to/pyproject.toml .

rm -rf *.egg-info
uv sync --reinstall
```

Then verify:

```bash
uv run bt-devices --help
uv run gps modems
uv run can interfaces
```

## pyproject changes

Two additions beyond the new entry point:

```toml
[project.optional-dependencies]
can = ["python-can>=4.0"]

[tool.setuptools.packages.find]
include = ["carlib*", "cli*"]
```

`packages.find` with a glob replaces the explicit list — subpackages are
picked up automatically as you add them.

python-can is **optional**, so `uv sync` alone does not install it. The
CAN module imports it lazily and raises a clear error if it is missing:

```bash
uv sync --extra can
```

---

# CAN bus

## Setup

```bash
sudo pacman -S can-utils
uv sync --extra can
```

Hardware needs a CAN transceiver — an MCP2515 HAT over SPI, or a USB
adapter. Then bring the interface up. Powertrain buses are usually
500 kbit/s, comfort buses 125 kbit/s:

```bash
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
```

For an MCP2515 HAT, add to `config.txt`:

```ini
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
```

Check the oscillator frequency on your board — 8 MHz and 16 MHz are both
common, and the wrong value gives you a bus that appears up but receives
nothing.

## Testing without a car

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

uv run can dump -c vcan0 &
cansend vcan0 1A0#1234ABCD
```

## Commands

```bash
uv run can interfaces               # what the kernel has
uv run can sniff --duration 30      # summarise an unknown bus
uv run can dump --id 1A0            # watch one ID
uv run can dump --limit 100 --json
uv run can send 1A0 1234ABCD -c vcan0
```

`sniff` is the starting point on an unfamiliar vehicle: it reports frame
rate, unique IDs, and the most recent payload per ID.

## Decoding

Arbitration IDs and bit packing are vehicle-specific and normally
reverse-engineered from a sniff. Register decoders and they apply
automatically in `dump` and `sniff`:

```python
from carlib.vehicle import can

@can.register(0x1A0)
def speed(frame):
    raw = int.from_bytes(frame.data[0:2], 'big')
    return [can.Signal('speed', raw * 0.01, 'km/h', raw)]
```

Put vehicle-specific decoders in their own module — say
`carlib/vehicle/decoders/volvo.py` — and import it where you need them.

## Safety

Writing to a live vehicle bus can trigger real behaviour: unlocking
doors, disabling systems, setting fault codes. Read-only until you know
what a frame does, and test sends on `vcan0`.

Many cars need a gateway bypass to reach the interesting buses from the
OBD-II port, and some monitor for unexpected traffic.

---

# Adding another domain later

The pattern, using OBD-II as an example:

1. `carlib/vehicle/obd.py` — dataclasses, async functions, raise from
   `carlib.core.errors`, no printing
2. If it needs a new D-Bus service, declare interfaces in
   `carlib/dbus/<service>.py` — never inside a domain module
3. `cli/obd.py` — thin, imports `carlib.core.output` for `run()` and
   `emit_json()`
4. Add the entry point to `[project.scripts]`
5. `uv sync --reinstall-package car-unit`

Imports flow downward only: `cli` → domain → `dbus`/`core` → `core`.
Nothing points back up, which is what keeps a future API process able to
import one domain without pulling in the rest.
