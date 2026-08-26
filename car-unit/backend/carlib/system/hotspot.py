"""
WiFi hotspot control.

The hotspot is hostapd, with dnsmasq (DHCP) and iptables (NAT) pulled
in by systemd -- hostapd Wants them, they BindsTo it, so starting and
stopping hostapd handles all three.

State comes from hostapd's control socket via hostapd_cli, which
reports what is actually running rather than what is configured. That
matters twice over: hostapd.conf is usually mode 600 because it holds
the passphrase, so parsing it as a normal user yields nothing; and with
automatic channel selection the configured channel is not the one in
use. The socket needs this in hostapd.conf:

    ctrl_interface=/run/hostapd
    ctrl_interface_group=wheel

The group line is what lets your user read it without sudo.

DHCP leases still come from dnsmasq's lease file -- hostapd knows who
is associated, but not what address they were given.

The Pi 4 has one radio, so an access point and a WiFi client cannot run
at once. Starting the hotspot therefore releases wlan0 from
NetworkManager with `nmcli device set wlan0 managed no`.

Do NOT use `nmcli radio wifi off` for that. It sets an rfkill soft
block on the whole phy, which blocks hostapd too -- and NetworkManager
persists the state, so the block comes back after every reboot.
`managed no` releases the interface without touching rfkill.
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

HOSTAPD_CLI = 'hostapd_cli'
HOSTAPD_CONF = Path('/etc/hostapd/hostapd.conf')

LEASE_FILES = (
    Path('/var/lib/misc/dnsmasq.leases'),
    Path('/var/lib/dnsmasq/dnsmasq.leases'),
)

NMCLI = 'nmcli'

# hostapd's own state machine. Only ENABLED means the AP is on the air.
STATE_ENABLED = 'ENABLED'


@dataclass
class Client:
    mac: str
    ip: str = ''
    hostname: str = ''
    expires: int = 0
    signal: int | None = None
    connected_time: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        return self.hostname or self.ip or self.mac


@dataclass
class HotspotState:
    active: bool = False
    ssid: str = ''
    bssid: str = ''
    channel: str = ''
    frequency: str = ''
    band: str = ''
    hostapd_state: str = ''
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
    def on_air(self) -> bool:
        """
        Running AND broadcasting.

        hostapd can be active as a unit while its interface sits in
        DISABLED -- typically an rfkill block or a channel it cannot
        use. That is a different failure from the service being down.
        """
        return self.active and self.hostapd_state == STATE_ENABLED

    @property
    def healthy(self) -> bool:
        """On the air with DHCP and NAT actually up behind it."""
        if not self.on_air:
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


# --- hostapd control socket ------------------------------------------------

def parse_kv(text: str) -> dict:
    """
    hostapd_cli emits flat key=value lines.

    Keys are indexed per-BSS (ssid[0], bssid[0]) since hostapd can run
    several on one radio; we only ever have one.
    """
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, _, value = line.partition('=')
        result[key.strip()] = value.strip()
    return result


def parse_stations(text: str) -> list[Client]:
    """
    Parse `hostapd_cli all_sta`.

    Each station starts with a bare MAC on its own line, followed by
    key=value lines until the next MAC.
    """
    clients = []
    current = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if re.fullmatch(r'[0-9a-f:]{17}', line, re.IGNORECASE):
            current = Client(mac=line.lower())
            clients.append(current)
            continue

        if current is None or '=' not in line:
            continue

        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip()

        if key == 'signal':
            try:
                current.signal = int(value)
            except ValueError:
                pass
        elif key == 'connected_time':
            try:
                current.connected_time = int(value)
            except ValueError:
                pass

    return clients


async def _cli(*args: str) -> str:
    """Run hostapd_cli against our interface."""
    return await _run(HOSTAPD_CLI, '-i', INTERFACE, *args, timeout=5.0)


async def hostapd_status() -> dict | None:
    """
    Live state from hostapd's control socket.

    Returns None when the socket is unreachable -- hostapd not running,
    or ctrl_interface not configured. That is different from hostapd
    running with a disabled interface, which returns a dict with
    state=DISABLED.
    """
    try:
        return parse_kv(await _cli('status'))
    except NotAvailableError:
        return None


async def hostapd_stations() -> list[Client] | None:
    """
    Associated stations, with signal strength.

    Returns None when the socket is unreachable, so callers can tell
    'nobody connected' from 'could not ask'.
    """
    try:
        return parse_stations(await _cli('all_sta'))
    except NotAvailableError:
        return None


def read_config() -> dict:
    """
    Fall back to hostapd.conf when the control socket is unavailable.

    Usually returns nothing: the file holds the passphrase and so is
    typically mode 600. Add ctrl_interface to hostapd.conf rather than
    relying on this.
    """
    result = {}
    if not HOSTAPD_CONF.exists():
        return result

    try:
        text = HOSTAPD_CONF.read_text(errors='replace')
    except PermissionError:
        return result

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        if key in ('ssid', 'channel', 'hw_mode', 'country_code'):
            result[key] = value.strip()

    return result


# --- DHCP leases -----------------------------------------------------------

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
            mac=parts[1].lower(),
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


# --- Interface and routing -------------------------------------------------

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


def band_from_freq(freq: str) -> str:
    try:
        mhz = int(freq)
    except (ValueError, TypeError):
        return ''
    if 2400 <= mhz < 2500:
        return '2.4 GHz'
    # 6E starts at 5925 MHz, so the 5 GHz band stops below it rather
    # than at a round 6000.
    if 5000 <= mhz < 5925:
        return '5 GHz'
    if mhz >= 5925:
        return '6 GHz'
    return ''


# --- Status ----------------------------------------------------------------

async def status() -> HotspotState:
    """Everything worth knowing about the hotspot in one call."""
    svc = await services.status('hotspot')

    state = HotspotState(
        active=svc.active,
        followers=svc.followers or {},
    )

    if not state.active:
        # Nothing live to read, so fall back to the configured SSID if
        # the file happens to be readable.
        config = read_config()
        state.ssid = config.get('ssid', '')
        state.channel = config.get('channel', '')
        return state

    hostapd = await hostapd_status()

    if hostapd is not None:
        state.hostapd_state = hostapd.get('state', '')
        state.ssid = hostapd.get('ssid[0]', '')
        state.bssid = hostapd.get('bssid[0]', '')
        state.channel = hostapd.get('channel', '')
        state.frequency = hostapd.get('freq', '')
        state.band = band_from_freq(state.frequency)
    else:
        # Socket unreachable. Report what the config says and assume
        # the interface is up, since the unit is active.
        config = read_config()
        state.ssid = config.get('ssid', '')
        state.channel = config.get('channel', '')
        state.band = {'g': '2.4 GHz', 'b': '2.4 GHz',
                      'a': '5 GHz'}.get(config.get('hw_mode', ''), '')
        state.hostapd_state = STATE_ENABLED

    state.address = await _interface_address()
    state.uplink = await _uplink()

    # hostapd is authoritative for who is associated; the lease file
    # only supplies the address and hostname. A lease outlives the
    # connection, so leases alone would report ghosts.
    stations = await hostapd_stations()
    leases = read_leases()
    by_mac = {c.mac: c for c in leases}

    if stations is None:
        state.clients = leases
        state.clients_verified = False
        return state

    state.clients_verified = True
    state.clients = []

    for station in stations:
        lease = by_mac.get(station.mac)
        if lease is not None:
            station.ip = lease.ip
            station.hostname = lease.hostname
            station.expires = lease.expires
        # An associated station with no lease is still connected --
        # it is on the air, just mid-DHCP.
        state.clients.append(station)

    state.clients.sort(key=lambda c: c.ip or c.mac)

    associated = {s.mac for s in stations}
    state.stale_leases = [c for c in leases if c.mac not in associated]

    return state


# --- Control ---------------------------------------------------------------

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


async def deauth(mac: str) -> None:
    """Kick a client off. It is free to reconnect immediately."""
    await _cli('deauthenticate', mac)
