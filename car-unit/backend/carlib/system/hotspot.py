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

# The unit behind the hotspot. Control goes through
# services.start('hotspot') so that services.FOLLOWERS applies; this is
# here for callers that need the unit name for a polkit rule or a
# systemd drop-in.
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
    stale_leases: list[Client] = field(default_factory=list)
    clients_verified: bool = True
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


async def associated_macs() -> list[str] | None:
    """
    MACs currently associated at the radio level.

    Returns None when the check itself could not run -- an empty list
    genuinely means nobody is connected, and conflating the two makes
    stale leases look like live clients.
    """
    try:
        out = await _run('iw', 'dev', INTERFACE, 'station', 'dump')
    except NotAvailableError:
        return None

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

    # A lease outlives the connection -- dnsmasq keeps it for the full
    # lease time whether or not the device is still on the air. So the
    # station dump decides who counts as connected; the lease only
    # supplies the address and hostname.
    leases = read_leases()
    associated = await associated_macs()

    if associated is None:
        # The check could not run (no iw, wrong interface). Report the
        # leases but flag that they are unverified rather than silently
        # implying they are live.
        state.clients = leases
        state.clients_verified = False
        return state

    by_mac = {c.mac.lower(): c for c in leases}
    state.clients_verified = True
    state.clients = []

    for mac in associated:
        mac = mac.lower()
        # An associated device with no lease yet still counts -- it is
        # on the air, just mid-DHCP.
        state.clients.append(by_mac.get(mac, Client(mac=mac)))

    state.clients.sort(key=lambda c: c.ip or c.mac)

    # Leases with no matching station: expired connections, useful to
    # show separately rather than as connected clients.
    state.stale_leases = [c for c in leases
                          if c.mac.lower() not in
                          {m.lower() for m in associated}]

    return state


async def _wait_for(active: bool, timeout: float = 10.0) -> bool:
    """
    Poll until hostapd reaches the wanted state.

    systemd's StartUnit and StopUnit return once the *job is queued*,
    not once the unit has settled. Reading status immediately reports
    the old value, which makes a toggle look like it did nothing.
    """
    waited = 0.0
    step = 0.25

    while waited < timeout:
        try:
            svc = await services.status('hotspot')
            if svc.active == active:
                # hostapd reports active before the AP is fully up;
                # a beat here means the client list is accurate too.
                await asyncio.sleep(0.3)
                return True
        except Exception:
            pass
        await asyncio.sleep(step)
        waited += step

    return False


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
    await _wait_for(True)
    return await status()


async def stop(restore_wifi: bool = True) -> HotspotState:
    """Stop the hotspot and hand wlan0 back to NetworkManager."""
    await services.stop('hotspot')
    await _wait_for(False)

    if restore_wifi:
        try:
            await _run(NMCLI, 'device', 'set', INTERFACE, 'managed', 'yes')
        except NotAvailableError:
            pass

    return await status()


async def toggle() -> HotspotState:
    current = await services.status('hotspot')
    if current.active:
        return await stop()
    return await start()


async def restart() -> HotspotState:
    await stop(restore_wifi=False)
    await asyncio.sleep(1.0)
    return await start()
