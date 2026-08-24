"""
WiFi hotspot control.

The hotspot is hostapd, with dnsmasq (DHCP) and iptables (NAT) pulled
in by systemd -- hostapd Wants them, they BindsTo it, so starting and
stopping hostapd handles all three.

The Pi 4 has one radio, so an access point and a WiFi client cannot run
at once. Starting the hotspot therefore releases wlan0 from
NetworkManager with `nmcli device set wlan0 managed no`.

Do NOT use `nmcli radio wifi off` for that. It sets an rfkill soft
block on the whole phy, which blocks hostapd too -- and NetworkManager
persists the state, so the block comes back after every reboot.
`managed no` releases the interface without touching rfkill.

Client leases are read from dnsmasq's lease file rather than over
D-Bus: dnsmasq's D-Bus interface does not expose them, and the file
format is stable.
"""

import re
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict

from carlib.core.errors import NotAvailableError
from carlib.system import services

UNIT = 'hostapd.service'
INTERFACE = 'wlan0'

HOSTAPD_CONF = Path('/etc/hostapd/hostapd.conf')
LEASE_FILES = (
    Path('/var/lib/misc/dnsmasq.leases'),
    Path('/var/lib/dnsmasq/dnsmasq.leases'),
)

NMCLI = 'nmcli'


@dataclass
class Client:
    mac: str
    ip: str = ''
    hostname: str = ''
    expires: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        return self.hostname or self.ip or self.mac


@dataclass
class HotspotState:
    active: bool = False
    ssid: str = ''
    channel: str = ''
    band: str = ''
    interface: str = INTERFACE
    address: str = ''
    uplink: str = ''
    clients: list[Client] = field(default_factory=list)
    followers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def client_count(self) -> int:
        return len(self.clients)

    @property
    def healthy(self) -> bool:
        """Running with DHCP and NAT actually up behind it."""
        if not self.active:
            return False
        return all(v == 'active' for v in self.followers.values())


async def _run(*args: str, timeout: float = 20.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(f'{args[0]} not found') from exc

    try:
        out, err = await asyncio.wait_for(proc.communicate(),
                                          timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError(f'timed out: {" ".join(args)}')

    if proc.returncode != 0:
        message = err.decode(errors='replace').strip() or 'unknown error'
        raise NotAvailableError(f'{args[0]} failed: {message}')

    return out.decode(errors='replace')


def read_config() -> dict:
    """Parse the handful of hostapd.conf keys worth reporting."""
    result = {}
    if not HOSTAPD_CONF.exists():
        return result

    try:
        text = HOSTAPD_CONF.read_text(errors='replace')
    except PermissionError:
        # hostapd.conf holds the passphrase, so it is often 0600.
        return result

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        if key in ('ssid', 'channel', 'hw_mode', 'country_code'):
            result[key] = value.strip()

    return result


def parse_leases(text: str) -> list[Client]:
    """
    dnsmasq lease format, one per line:

        <expiry> <mac> <ip> <hostname> <client-id>

    Hostname is '*' when the client did not send one.
    """
    clients = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            expires = int(parts[0])
        except ValueError:
            continue

        hostname = parts[3]
        clients.append(Client(
            mac=parts[1],
            ip=parts[2],
            hostname='' if hostname == '*' else hostname,
            expires=expires,
        ))

    clients.sort(key=lambda c: c.ip)
    return clients


def read_leases(subnet_prefix: str = '192.168.50.') -> list[Client]:
    """
    Current DHCP leases, filtered to the hotspot subnet.

    The lease file is shared with any other dnsmasq instance, so the
    prefix filter avoids reporting unrelated clients.
    """
    for path in LEASE_FILES:
        if not path.exists():
            continue
        try:
            text = path.read_text(errors='replace')
        except PermissionError:
            return []
        return [c for c in parse_leases(text)
                if c.ip.startswith(subnet_prefix)]
    return []


async def associated_macs() -> list[str]:
    """
    MACs currently associated at the radio level.

    A device can hold a lease after disconnecting, so this is the
    authoritative list of who is actually on the air.
    """
    try:
        out = await _run('iw', 'dev', INTERFACE, 'station', 'dump')
    except NotAvailableError:
        return []

    return re.findall(r'Station ([0-9a-f:]{17})', out, re.IGNORECASE)


async def _interface_address() -> str:
    try:
        out = await _run('ip', '-4', 'addr', 'show', INTERFACE)
    except NotAvailableError:
        return ''
    match = re.search(r'inet ([\d.]+)', out)
    return match.group(1) if match else ''


async def _uplink() -> str:
    """Which interface the Pi's default route currently uses."""
    try:
        out = await _run('ip', 'route', 'get', '1.1.1.1')
    except NotAvailableError:
        return ''
    match = re.search(r'\bdev\s+(\S+)', out)
    return match.group(1) if match else ''


async def status() -> HotspotState:
    """Everything worth knowing about the hotspot in one call."""
    svc = await services.status('hotspot')

    state = HotspotState(
        active=svc.active,
        followers=svc.followers or {},
    )

    config = read_config()
    state.ssid = config.get('ssid', '')
    state.channel = config.get('channel', '')
    mode = config.get('hw_mode', '')
    state.band = {'g': '2.4 GHz', 'b': '2.4 GHz',
                  'a': '5 GHz'}.get(mode, mode)

    if not state.active:
        return state

    state.address = await _interface_address()
    state.uplink = await _uplink()

    # Only report clients that are both leased and associated.
    leases = read_leases()
    associated = {m.lower() for m in await associated_macs()}
    if associated:
        state.clients = [c for c in leases
                         if c.mac.lower() in associated]
    else:
        state.clients = leases

    return state


async def start() -> HotspotState:
    """
    Bring the hotspot up, releasing wlan0 from NetworkManager first.

    NetworkManager releases asynchronously, so hostapd needs a moment
    before the interface is genuinely free.
    """
    try:
        await _run(NMCLI, 'device', 'set', INTERFACE, 'managed', 'no')
        await asyncio.sleep(1.0)
    except NotAvailableError:
        pass        # NetworkManager may not be managing it at all

    await services.start('hotspot')
    return await status()


async def stop(restore_wifi: bool = True) -> HotspotState:
    """Stop the hotspot and hand wlan0 back to NetworkManager."""
    await services.stop('hotspot')

    if restore_wifi:
        try:
            await _run(NMCLI, 'device', 'set', INTERFACE, 'managed', 'yes')
        except NotAvailableError:
            pass

    return await status()


async def toggle() -> HotspotState:
    current = await status()
    return await (stop() if current.active else start())


async def restart() -> HotspotState:
    await stop(restore_wifi=False)
    await asyncio.sleep(1.0)
    return await start()
