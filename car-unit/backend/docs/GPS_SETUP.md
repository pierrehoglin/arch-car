# GPS setup — packages and file placement

## 1. Packages

```bash
sudo pacman -S --needed modemmanager libqmi usb_modeswitch
```

| Package | Why |
|---|---|
| `modemmanager` | The daemon. Provides `mmcli` and the D-Bus interfaces `carlib.location.gps` uses. |
| `libqmi` | QMI protocol support. ModemManager needs it to talk to the SIM7600 over `cdc-wdm0`. Also gives you `qmicli` for debugging. |
| `usb_modeswitch` | Puts the HAT into its data mode on plug-in. Usually automatic, but without it the modem sometimes enumerates as storage only. |

Optional, for AT-command debugging:

```bash
sudo pacman -S minicom
```

You do **not** need `gpsd`. ModemManager reads the GPS itself, and
running both means two daemons fighting over `/dev/ttyUSB1` — the same
class of conflict as oFono and WirePlumber over HFP.

Nothing new on the Python side: `sdbus` is already a dependency.

## 2. Enable the service

```bash
sudo systemctl enable --now ModemManager
mmcli -L
```

You should see your SIM7600E-H. If not, check `ls /dev/cdc-wdm0`.

## 3. Drop the sudo requirement

Without this every `gps` command needs `sudo`, which also blocks a
future API service from reading position.

```bash
sudo tee /etc/polkit-1/rules.d/50-modemmanager.rules > /dev/null <<'EOF'
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.ModemManager1.") === 0 &&
        subject.user == "alarm") {
        return polkit.Result.YES;
    }
});
EOF
sudo systemctl restart polkit
```

Test: `mmcli -m 0 --location-status` should work without `sudo`.

---

# 4. File placement

## Target structure

```
backend/
├── pyproject.toml
├── uv.lock
├── carlib/
│   ├── __init__.py
│   ├── core/          errors.py  match.py  output.py
│   ├── dbus/          connection.py  variants.py  bluez.py
│   │                  ofono.py  obex.py
│   │                  modemmanager.py        <-- GPS
│   ├── bluetooth/     calls.py  media.py
│   │                  phonebook.py  messages.py
│   ├── location/      gps.py                 <-- GPS
│   └── vehicle/       can.py
└── cli/
    ├── __init__.py
    ├── bt_call.py     bt_media.py    bt_devices.py
    ├── bt_phonebook.py               bt_messages.py
    ├── gps.py                        <-- GPS
    └── can.py
```

## The three GPS files

| File | Goes in |
|---|---|
| `modemmanager.py` | `carlib/dbus/` |
| `gps.py` (imports `carlib.dbus.modemmanager`) | `carlib/location/` |
| `gps.py` (imports `argparse`) | `cli/` |

Two files are named `gps.py`. The library one imports
`carlib.dbus.modemmanager`; the CLI one imports `argparse`. Anything
importing `argparse` belongs in `cli/`.

## Add the entry point

In `pyproject.toml`, under `[project.scripts]`:

```toml
[project.scripts]
bt-call      = "cli.bt_call:main"
bt-media     = "cli.bt_media:main"
bt-devices   = "cli.bt_devices:main"
bt-phonebook = "cli.bt_phonebook:main"
bt-messages  = "cli.bt_messages:main"
gps          = "cli.gps:main"
```

Then rebuild — entry-point changes are one of the few things that
require a re-sync:

```bash
uv sync --reinstall-package car-unit
uv run gps modems
```

---

# 5. Files to delete

These are the pre-refactor monoliths, superseded by `carlib/` plus
`cli/`. They still work standalone, but each declares its own copies of
the same D-Bus interfaces — so importing two of them into one process
hits the sdbus registry collision. Once the new CLIs behave the same on
hardware, remove them:

```bash
cd backend
rm -f legacy/bt_call.py legacy/bt_devices.py legacy/bt_media.py
rm -f legacy/bt_phonebook.py legacy/bt_messages.py legacy/dbus_explore.py
rmdir legacy 2>/dev/null
```

Also clear the stale build artefact from the earlier project name:

```bash
rm -rf dbus_api.egg-info car_unit.egg-info
uv sync --reinstall
```

If you kept any hyphenated copies (`bt-call`, `bt-call.py`), delete
those too — only the underscore versions in `cli/` are importable.

---

# 6. First run

```bash
uv run gps modems          # confirm capabilities include gps-nmea
uv run gps enable          # turn on NMEA + raw
uv run gps rate 1          # 30s default is useless in a car
uv run gps status          # verify what took effect
uv run gps get             # will say "no fix" at first
uv run gps sats            # satellites being tracked
```

A cold start takes **several minutes** with the antenna outdoors and a
clear view of sky. `gps sats` showing satellites with rising SNR means
it is working even before a fix arrives.

Once you have a fix:

```bash
uv run gps watch           # live updates
uv run gps get --json      # for scripting
```

## When the SIM data works

A-GPS cuts cold-start time from minutes to seconds:

```bash
uv run gps supl supl.google.com:7275
uv run gps enable --assisted
```

Needs a working data connection, so leave this until the SIM is sorted.

---

# 7. Optional: enable GPS at boot

Location gathering does not persist across reboots.

`~/.config/systemd/user/gps-enable.service`

```ini
[Unit]
Description=Enable GPS location gathering
After=graphical-session.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=%h/car-unit/backend/.venv/bin/gps enable
ExecStart=%h/car-unit/backend/.venv/bin/gps rate 1

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gps-enable
```

A user unit, matching the rest of your setup. Requires the polkit rule
from section 3 — without it the service fails with an authorisation
error.

---

# 8. Troubleshooting

**`mmcli -L` shows nothing**
Modem in the wrong USB mode. Check `ls /dev/ttyUSB*` — if those exist
but `cdc-wdm0` does not:
```bash
sudo systemctl stop ModemManager
minicom -D /dev/ttyUSB2 -b 115200
# AT+CUSBPIDSWITCH=9001,1,1     (module reboots, 15-30s)
sudo systemctl start ModemManager
```

**`error: cannot read location` mentioning polkit**
Section 3 rule missing or polkit not restarted.

**`gps watch` blocks forever**
Signalling is off. Re-run `gps enable`, which sets it, then check
`gps status` shows `signals changes: True`.

**No fix after 15 minutes outdoors**
Check the GPS antenna is on the **GNSS** connector, not the LTE one —
they are physically identical on the HAT. `gps sats` reporting nothing
at all points at the antenna; satellites with low SNR points at
placement.

**`gps get` shows cell location but no GPS**
Normal before first fix. The `3gpp-lac-ci` source works immediately
because it comes from the tower, not satellites.
