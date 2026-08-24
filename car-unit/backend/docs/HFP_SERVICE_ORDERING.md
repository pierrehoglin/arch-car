# HFP service ordering: bluetooth -> ofono -> wireplumber

The problem: oFono registers the HFP profile UUID with BlueZ at startup.
If WirePlumber gets there first, oFono's `RegisterProfile()` fails with
`org.bluez.Error.NotPermitted, UUID already registered`, and every
subsequent `ConnectProfile()` returns `ProfileUnavailable`. The modem
then shows up in `GetModems` but with an empty `Interfaces` list and
`SetProperty Powered` fails.

Ordering fixes it permanently so you don't have to restart things by
hand after every boot.

---

## 1. WirePlumber must defer HFP to oFono

This is the config you already have. Included for completeness, because
the ordering below is pointless without it.

`~/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf`

```
monitor.bluez.properties = {
  bluez5.hfphsp-backend = "ofono"
}
```

For WirePlumber 0.4.x the equivalent is Lua, at
`~/.config/wireplumber/bluetooth.lua.d/51-bluez-config.lua`:

```lua
bluez_monitor.properties = {
  ["bluez5.hfphsp-backend"] = "ofono",
}
```

Check with `wireplumber --version` if unsure.

---

## 2. oFono after BlueZ

`/etc/systemd/system/ofono.service.d/ordering.conf`

```ini
[Unit]
After=bluetooth.service
Wants=bluetooth.service
PartOf=bluetooth.service

[Service]
# BlueZ takes a moment to be ready to accept profile registrations even
# after the unit reports started. Without this, RegisterProfile races
# and loses.
ExecStartPre=/usr/bin/sleep 2
Restart=on-failure
RestartSec=3
```

`PartOf` means restarting `bluetooth` also restarts `ofono`, which keeps
the registration valid — otherwise a BlueZ restart silently orphans
oFono's profile.

Enable it (Arch ships it disabled):

```bash
sudo systemctl enable ofono
```

---

## 3. WirePlumber after oFono

WirePlumber is a **user** unit, oFono is a **system** unit, so systemd
cannot order them directly — user units can't declare `After=` on system
units.

Two approaches. The second is more robust.

### 3a. Delay only (simple, usually enough)

`~/.config/systemd/user/wireplumber.service.d/ordering.conf`

```ini
[Service]
ExecStartPre=/usr/bin/sleep 3
```

Crude, but it works because oFono only needs to have registered its
profile, which happens within a second or two of starting.

### 3b. Wait for oFono on the system bus (preferred)

`~/.local/bin/wait-for-ofono`

```bash
#!/bin/sh
# Block until oFono owns its bus name, or give up after 15s.
i=0
while [ $i -lt 30 ]; do
    if busctl --system status org.ofono >/dev/null 2>&1; then
        exit 0
    fi
    sleep 0.5
    i=$((i + 1))
done
# Don't block the session forever if ofono is absent or broken.
exit 0
```

```bash
chmod +x ~/.local/bin/wait-for-ofono
```

`~/.config/systemd/user/wireplumber.service.d/ordering.conf`

```ini
[Service]
ExecStartPre=%h/.local/bin/wait-for-ofono
```

The unconditional `exit 0` at the end matters: if oFono is uninstalled
or failing, you still want audio rather than a session that won't start.

---

## 4. Apply

```bash
sudo mkdir -p /etc/systemd/system/ofono.service.d
mkdir -p ~/.config/systemd/user/wireplumber.service.d

# ... create the files above ...

sudo systemctl daemon-reload
systemctl --user daemon-reload
sudo systemctl enable ofono
```

Then reboot and verify — the point of this is that it survives a reboot
without manual intervention.

---

## 5. Verify

```bash
# Ordering actually took effect
systemd-analyze verify /etc/systemd/system/ofono.service.d/ordering.conf
systemctl show ofono -p After | tr ' ' '\n' | grep bluetooth

# No registration conflict
sudo journalctl -u ofono -b | grep -i 'registerprofile\|already registered'

# WirePlumber isn't fighting for HFP
journalctl --user -u wireplumber -b | grep -i ofono

# The modem came up with its interfaces
sudo busctl --system call org.ofono / org.ofono.Manager GetModems
```

What you want to see:

- No `UUID already registered` in the oFono log
- No `ofono running, but not configured as HFP/HSP backend` from
  WirePlumber
- `Interfaces` containing `org.ofono.VoiceCallManager` once the phone is
  connected

If `Interfaces` is still empty after a reboot, the phone connected
before oFono registered. That's the next section.

---

## 6. Bring the modem online when the phone connects

Ordering the services isn't quite enough: the HFP link is established at
Bluetooth connect time, and `Powered`/`Online` default to false. A udev-
style trigger would be ideal but BlueZ connections aren't udev events, so
watch D-Bus instead.

`~/.local/bin/ofono-autoconnect`

```bash
#!/bin/sh
# Bring every HFP modem online as it appears.
busctl --system monitor org.ofono 2>/dev/null | while read -r line; do
    case "$line" in
        *ModemAdded*|*PropertiesChanged*)
            for path in $(busctl --system call org.ofono / \
                    org.ofono.Manager GetModems 2>/dev/null \
                    | grep -o '/hfp/[^"]*'); do
                busctl --system call org.ofono "$path" \
                    org.ofono.Modem SetProperty sv Powered b true 2>/dev/null
                busctl --system call org.ofono "$path" \
                    org.ofono.Modem SetProperty sv Online b true 2>/dev/null
            done
            ;;
    esac
done
```

This is the crude version. The robust one is a small Python service using
the `ofono.Manager.ModemAdded` signal — the same pattern as
`bt_call.py monitor` — which is worth writing if you go ahead with the
unified daemon.

Running it as a system service needs root for the oFono calls, or the
D-Bus policy in the next section.

---

## 7. Optional: drop sudo for oFono

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

Then `bt_call.py` runs unprivileged, and the autoconnect script can run
as a user unit alongside WirePlumber.
