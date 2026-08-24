"""
Service control: SSH, Bluetooth, hotspot.

Each is a named service with a couple of units behind it. The hotspot
in particular is hostapd plus dnsmasq plus iptables, but only hostapd is
named here -- the other two follow via BindsTo, so starting hostapd
starts all three. See HFP_SERVICE_ORDERING.md for that pattern.

Authorisation goes through polkit. Put this in
/etc/polkit-1/rules.d/50-carunit.rules:

    polkit.addRule(function(action, subject) {
        if (action.id == "org.freedesktop.systemd1.manage-units" &&
            subject.user == "alarm") {
            var unit = action.lookup("unit");
            if (unit == "sshd.service" ||
                unit == "bluetooth.service" ||
                unit == "hostapd.service" ||
                unit == "iwd.service") {
                return polkit.Result.YES;
            }
        }
    });

then `sudo systemctl restart polkit`. Note polkit silently ignores
rules with syntax errors -- check `journalctl -u polkit` if a call
still fails.
"""

from dataclasses import dataclass, asdict

from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.dbus import systemd

# Friendly name -> the unit that fronts it. Units that follow via
# BindsTo are deliberately absent: starting the front unit is enough,
# and naming them here would mean extra polkit grants for no gain.
SERVICES = {
    'ssh': 'sshd.service',
    'bluetooth': 'bluetooth.service',
    'hotspot': 'hostapd.service',
    'wifi': 'iwd.service',
}

# Units that come up with the front unit but are not controlled
# directly. Reported by `status` so the picture is complete.
FOLLOWERS = {
    'hotspot': ('dnsmasq.service', 'iptables.service'),
}


@dataclass
class ServiceState:
    name: str
    unit: str
    active: bool = False
    active_state: str = 'unknown'
    sub_state: str = ''
    enabled: str = ''
    description: str = ''
    followers: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def enabled_at_boot(self) -> bool:
        return self.enabled in ('enabled', 'enabled-runtime',
                                'static', 'indirect')


def resolve_unit(name: str) -> str:
    """Map a friendly name to a unit, or pass a unit name through."""
    if name in SERVICES:
        return SERVICES[name]
    if name.endswith('.service') or '.' in name:
        return name
    raise NotFoundError('service', name, sorted(SERVICES))


async def _unit_state(unit: str) -> dict:
    path = await systemd.unit_path(unit)
    proxy = systemd.unit_proxy(path)
    return {
        'active_state': await proxy.active_state,
        'sub_state': await proxy.sub_state,
        'enabled': await proxy.unit_file_state,
        'description': await proxy.description,
    }


async def status(name: str) -> ServiceState:
    """Current state of one service."""
    unit = resolve_unit(name)
    info = await _unit_state(unit)

    followers = None
    if name in FOLLOWERS:
        followers = {}
        for follower in FOLLOWERS[name]:
            try:
                sub = await _unit_state(follower)
                followers[follower] = sub['active_state']
            except Exception:
                followers[follower] = 'not-found'

    return ServiceState(
        name=name,
        unit=unit,
        active=info['active_state'] == 'active',
        active_state=info['active_state'],
        sub_state=info['sub_state'],
        enabled=info['enabled'],
        description=info['description'],
        followers=followers,
    )


async def status_all() -> list[ServiceState]:
    result = []
    for name in SERVICES:
        try:
            result.append(await status(name))
        except Exception:
            result.append(ServiceState(name=name, unit=SERVICES[name],
                                       active_state='not-found'))
    return result


async def start(name: str) -> ServiceState:
    unit = resolve_unit(name)
    try:
        await systemd.manager().start_unit(unit, systemd.MODE_REPLACE)
    except Exception as exc:
        raise NotAvailableError(
            f'cannot start {unit}: {exc}',
            hint='if this is a polkit error, add a rule granting '
                 'org.freedesktop.systemd1.manage-units for this '
                 'unit -- see carlib/system/services.py') from exc
    return await status(name)


async def stop(name: str) -> ServiceState:
    unit = resolve_unit(name)
    try:
        await systemd.manager().stop_unit(unit, systemd.MODE_REPLACE)
    except Exception as exc:
        raise NotAvailableError(f'cannot stop {unit}: {exc}') from exc
    return await status(name)


async def restart(name: str) -> ServiceState:
    unit = resolve_unit(name)
    try:
        await systemd.manager().restart_unit(unit, systemd.MODE_REPLACE)
    except Exception as exc:
        raise NotAvailableError(f'cannot restart {unit}: {exc}') from exc
    return await status(name)


async def toggle(name: str) -> ServiceState:
    current = await status(name)
    return await (stop(name) if current.active else start(name))


async def set_enabled(name: str, enabled: bool) -> ServiceState:
    """
    Enable or disable at boot. Separate from start/stop.

    Needs a different polkit action
    (org.freedesktop.systemd1.manage-unit-files), so a rule permitting
    start/stop will not cover this.
    """
    unit = resolve_unit(name)
    mgr = systemd.manager()
    try:
        if enabled:
            await mgr.enable_unit_files([unit], False, False)
        else:
            await mgr.disable_unit_files([unit], False)
    except Exception as exc:
        raise NotAvailableError(
            f'cannot change boot state of {unit}: {exc}',
            hint='needs the manage-unit-files polkit action, which is '
                 'separate from manage-units') from exc
    return await status(name)


# --- Hotspot --------------------------------------------------------------
#
# Hotspot control lives in carlib.system.hotspot, which knows about the
# radio conflict, the DHCP leases and the uplink. It is not just a
# service start.
#
# The earlier versions here stopped iwd to free the interface. That is
# wrong once NetworkManager owns the radio: NM starts iwd as its
# backend and restarts it, so stopping the unit achieves nothing. Use
# `nmcli device set wlan0 managed no` instead -- and never
# `nmcli radio wifi off`, which rfkill-blocks the whole phy and
# persists across reboots.
