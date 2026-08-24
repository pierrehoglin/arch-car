# car-unit backend — build and deploy

From a bare Arch Linux ARM system to a working install.

---

## 1. System packages

These cannot live in the venv. `sdbus` compiles a C extension against
libsystemd, so the headers and toolchain must be system-wide.

```bash
sudo pacman -S --needed \
    base-devel python systemd \
    bluez bluez-utils bluez-obex \
    ofono \
    uv
```

`systemd` (not just `systemd-libs`) provides `systemd/sd-bus.h`, which
the build needs.

---

## 2. Services

```bash
sudo systemctl enable --now bluetooth
sudo systemctl enable --now ofono
systemctl --user enable --now obex
```

`obex` is a **user** unit — it runs on the session bus, which is why
phonebook and message access need a user session rather than a system
service.

### WirePlumber must defer HFP to oFono

Without this, WirePlumber and oFono fight over the HFP profile and
`SetProperty Powered` fails.

```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cat > ~/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf <<'EOF'
monitor.bluez.properties = {
  bluez5.hfphsp-backend = "ofono"
}
EOF
systemctl --user restart wireplumber
```

Start order matters: **bluetooth → ofono → wireplumber**. See
`HFP_SERVICE_ORDERING.md` for the drop-ins that make it survive a reboot.

### Optional: drop sudo for oFono

```bash
sudo tee /etc/dbus-1/system.d/ofono-user.conf > /dev/null <<'EOF'
<busconfig>
  <policy user="alarm">
    <allow send_destination="org.ofono"/>
  </policy>
</busconfig>
EOF
sudo systemctl reload dbus
```

Without this, `bt-call` needs `sudo`.

---

## 3. Project layout

```
backend/
├── pyproject.toml
├── uv.lock
├── carlib/
│   ├── __init__.py
│   ├── core/          errors.py  match.py  output.py
│   ├── dbus/          connection.py  variants.py
│   │                  bluez.py  ofono.py  obex.py  modemmanager.py
│   ├── bluetooth/     calls.py  media.py  phonebook.py  messages.py
│   ├── location/      gps.py
│   └── vehicle/       can.py
└── cli/
    ├── __init__.py
    ├── bt_call.py     bt_media.py    bt_devices.py
    ├── bt_phonebook.py               bt_messages.py
    └── gps.py         can.py
```

Every directory needs `__init__.py`, including each `carlib`
subpackage. Module filenames use **underscores** even though the
commands are hyphenated — the mapping happens in `[project.scripts]`.

See `RESTRUCTURE.md` for why the package is split this way.

---

## 4. Build

```bash
cd backend
uv sync
```

That creates `.venv`, installs sdbus, and installs the project editable
in one step. Do not run `uv pip install` separately — `uv sync` reads
`dependencies` from `pyproject.toml`.

Verify:

```bash
uv run bt-devices --help
ls .venv/bin/bt-*
```

---

## 5. Everyday use

```bash
uv run bt-devices
uv run bt-call modems
uv run bt-media players
```

Or activate once:

```bash
source .venv/bin/activate
bt-devices
```

---

## 6. Rebuilding after changes

Editable installs pick up edits to module contents automatically. You
only need to re-sync when the **packaging** changes:

| Change | Command |
|---|---|
| Edited a `.py` file | nothing |
| Added a new module | nothing |
| Added or renamed an entry point | `uv sync --reinstall-package car-unit` |
| Added a dependency | `uv add <pkg>` |
| Removed a dependency | `uv remove <pkg>` |
| Something is stale and you don't know why | `uv sync --reinstall` |

```bash
# nuclear option
rm -rf .venv *.egg-info
uv sync
```

---

## 7. Deploying to another Pi

`uv.lock` pins exact versions, so commit it.

```bash
# on the target
git clone <repo> ~/car-unit
cd ~/car-unit/backend
uv sync --frozen
```

`--frozen` installs exactly what the lockfile says and refuses to
re-resolve. That is what you want on a device — identical versions to
what you tested.

---

## 8. Running as a systemd service

Call the venv binary directly. `uv run` re-resolves the environment on
each invocation, which is wasted startup time in a service.

`~/.config/systemd/user/bt-monitor.service`

```ini
[Unit]
Description=Bluetooth call monitor
After=graphical-session.target

[Service]
Type=simple
ExecStart=%h/car-unit/backend/.venv/bin/bt-call monitor
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now bt-monitor
journalctl --user -u bt-monitor -f
```

A **user** unit, not a system one: obexd needs the session bus, and
`DBUS_SESSION_BUS_ADDRESS` is not set for system services.

If you want it running without a login session:

```bash
sudo loginctl enable-linger alarm
```

---

## 9. Verifying the whole stack

```bash
# services
systemctl is-active bluetooth ofono
systemctl --user is-active obex wireplumber

# no HFP profile conflict
sudo journalctl -u ofono -b | grep -i 'already registered' && echo "CONFLICT"
journalctl --user -u wireplumber -b | grep -i 'not configured as HFP'

# the library sees hardware
uv run bt-devices
uv run bt-call modems          # Interfaces must list VoiceCallManager
uv run bt-media players
uv run bt-phonebook <MAC> --size
uv run bt-messages <MAC> folders
```

`bt-call modems` showing an empty `interfaces` list is the usual
failure. Run `uv run bt-call online`, and if that fails restart in order:

```bash
sudo systemctl restart bluetooth
sleep 2
sudo systemctl restart ofono
systemctl --user restart wireplumber
```

---

## 10. Exit codes

Useful when scripting against these:

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Other error |
| 2 | Not found |
| 3 | Ambiguous match |
| 4 | Service not available |
| 5 | Transfer failed |
| 130 | Interrupted |

---

## Adding the API later

```bash
uv add fastapi uvicorn
```

```toml
[project.scripts]
car-api = "api.main:run"
```

```toml
[tool.setuptools]
include = ["carlib*", "cli*", "api*"]
```

Then `uv sync --reinstall-package car-unit`. `carlib` is already a proper
package in the same project, so the API imports it with no path handling.

---

## Common problems

**`ModuleNotFoundError: No module named 'cli.bt_devices'`**
Filenames use hyphens. Rename to underscores:
`for f in cli/bt-*.py; do mv "$f" "$(echo $f | tr '-' '_')"; done`

**Command not found after `uv sync`**
Missing `[tool.uv] package = true`, or a missing `__init__.py` in `cli/`.

**sdbus build fails on `systemd/sd-bus.h`**
Install `systemd`, not just `systemd-libs`.

**sdbus builds but misbehaves at runtime**
uv's managed CPython may not match system libsystemd. Pin the system
interpreter:

```toml
[tool.uv]
package = true
python-preference = "only-system"
```

**Stale `*.egg-info` from an earlier project name**
`rm -rf *.egg-info && uv sync --reinstall`
