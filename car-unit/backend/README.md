# car-unit docs

Reference material for the Raspberry Pi 4 car unit: Arch Linux ARM,
Waveshare 10.1" DSI panel, Wayfire desktop, and the `carlib` Python
package for Bluetooth, GPS and CAN.

## Read in this order

| Document | Covers |
|---|---|
| [RESTRUCTURE.md](docs/RESTRUCTURE.md) | Package layout and why the boundaries are where they are. Start here. |
| [BUILD_AND_DEPLOY.md](docs/BUILD_AND_DEPLOY.md) | Bare system to working install with uv. Rebuild rules, deployment, systemd units. |
| [BT_COMMANDS.md](docs/BT_COMMANDS.md) | Every CLI command, plus a feature roadmap. |
| [GPS_SETUP.md](docs/GPS_SETUP.md) | ModemManager packages, polkit rule, file placement, troubleshooting. |
| [HFP_SERVICE_ORDERING.md](docs/HFP_SERVICE_ORDERING.md) | Why bluetooth → ofono → wireplumber ordering matters, and the drop-ins that enforce it. |

## Hard-won details worth not rediscovering

**HFP profile registration races.** oFono and WirePlumber both want the
HFP UUID. WirePlumber must be told to defer (`bluez5.hfphsp-backend =
"ofono"`), and the start order matters. Masking `plymouth-quit` or
replacing it with `/bin/true` deadlocks the boot, because
`plymouth-quit-wait` blocks forever waiting for a daemon that never
exits. See HFP_SERVICE_ORDERING.md.

**oFono on the critical path.** `WantedBy=multi-user.target` puts it in
front of `graphical.target` and costs ~2s of boot. Wiring it to
`bluetooth.service` instead takes it off the path entirely.

**sdbus interface names are globally unique per process.** Declaring
`org.freedesktop.DBus.Properties` or `ObjectManager` yourself raises
`ValueError` — sdbus already provides both. This is why every interface
lives in `carlib/dbus/` and is declared exactly once.

**ModemManager indices are ephemeral.** `Modem/0` becomes `Modem/1`
after a restart. Use `mmcli -m any`, and note that `carlib` resolves
dynamically for this reason.

**Location gathering does not persist.** It resets whenever
ModemManager restarts, hence the boot-time user unit in GPS_SETUP.md.

**The DSI panel does not exist for the first ~2.8s of boot.** Nothing
can be displayed before the panel driver, its I2C MCU and the rails come
up — no splash, no console. Plymouth covers from ~3s onward.
