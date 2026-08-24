"""
WiFi control via NetworkManager.

This module shells out to nmcli rather than using NetworkManager's
D-Bus API directly, which deserves an explanation given everything else
here is D-Bus.

Connecting to a new network over D-Bus means calling
AddAndActivateConnection with a nested a{sa{sv}} settings dictionary --
every key typed, every value a variant, and the required keys differing
by security type (WPA-PSK, WPA-EAP, SAE, open). Getting one signature
wrong produces an opaque failure. nmcli constructs that dictionary
correctly, handles secrets, and reuses an existing profile if the SSID
is already known.

nmcli's terse mode (-t -f) is stable, machine-readable output designed
for exactly this. Subprocesses run through asyncio, so nothing blocks.

Note this system uses iwd as NetworkManager's backend
(/etc/NetworkManager/conf.d/wifi_backend.conf). That is transparent to
nmcli -- do not talk to iwd directly, or the two will fight over the
interface.
"""

import asyncio
from dataclasses import dataclass, asdict

from carlib.core.errors import NotAvailableError, NotFoundError

NMCLI = 'nmcli'
SCAN_SETTLE = 2.0


@dataclass
class Network:
    ssid: str
    signal: int = 0
    security: str = ''
    channel: str = ''
    rate: str = ''
    in_use: bool = False
    saved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def open(self) -> bool:
        return self.security in ('', '--')

    @property
    def bars(self) -> str:
        """Signal as a five-step bar, for a status display."""
        filled = min(5, max(0, round(self.signal / 20)))
        return '#' * filled + '.' * (5 - filled)


@dataclass
class WifiState:
    enabled: bool = False
    connected: bool = False
    ssid: str = ''
    signal: int = 0
    ip_address: str = ''
    device: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


async def _run(*args: str, timeout: float = 30.0) -> str:
    """Run nmcli and return stdout, raising on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            NMCLI, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            'nmcli not found',
            hint='install networkmanager') from exc

    try:
        out, err = await asyncio.wait_for(proc.communicate(),
                                          timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError(f'nmcli timed out: {" ".join(args)}')

    if proc.returncode != 0:
        message = err.decode(errors='replace').strip() or 'unknown error'
        raise NotAvailableError(f'nmcli failed: {message}')

    return out.decode(errors='replace')


def _split(line: str) -> list[str]:
    """
    Split an nmcli terse line on unescaped colons.

    SSIDs legitimately contain colons, and nmcli escapes them as \\:
    """
    fields = []
    current = []
    escaped = False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == '\\':
            escaped = True
        elif ch == ':':
            fields.append(''.join(current))
            current = []
        else:
            current.append(ch)
    fields.append(''.join(current))
    return fields


async def saved_networks() -> list[str]:
    """SSIDs with a stored profile."""
    out = await _run('-t', '-f', 'NAME,TYPE', 'connection', 'show')
    names = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = _split(line)
        if len(parts) >= 2 and 'wireless' in parts[1]:
            names.append(parts[0])
    return names


async def scan(rescan: bool = True) -> list[Network]:
    """
    Available networks, strongest first.

    rescan forces a fresh scan, which takes a couple of seconds. Pass
    False to use NetworkManager's cached list for a snappier UI.
    """
    if rescan:
        try:
            await _run('device', 'wifi', 'rescan', timeout=15.0)
            await asyncio.sleep(SCAN_SETTLE)
        except NotAvailableError:
            pass        # a scan already in progress is not an error

    out = await _run('-t', '-f',
                     'IN-USE,SSID,SIGNAL,SECURITY,CHAN,RATE',
                     'device', 'wifi', 'list')

    known = set(await saved_networks())
    networks = []
    seen = set()

    for line in out.splitlines():
        if not line.strip():
            continue
        parts = _split(line)
        if len(parts) < 4:
            continue

        ssid = parts[1]
        if not ssid or ssid in seen:
            continue        # hidden networks and duplicate BSSIDs
        seen.add(ssid)

        try:
            signal = int(parts[2])
        except (ValueError, IndexError):
            signal = 0

        networks.append(Network(
            ssid=ssid,
            signal=signal,
            security=parts[3] if len(parts) > 3 else '',
            channel=parts[4] if len(parts) > 4 else '',
            rate=parts[5] if len(parts) > 5 else '',
            in_use=parts[0].strip() == '*',
            saved=ssid in known,
        ))

    networks.sort(key=lambda n: n.signal, reverse=True)
    return networks


async def status() -> WifiState:
    """Whether wifi is on, and what it is connected to."""
    radio = (await _run('-t', 'radio', 'wifi')).strip()
    state = WifiState(enabled=radio == 'enabled')

    out = await _run('-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION',
                     'device', 'status')
    for line in out.splitlines():
        parts = _split(line)
        if len(parts) >= 4 and parts[1] == 'wifi':
            state.device = parts[0]
            state.connected = parts[2] == 'connected'
            state.ssid = parts[3] if state.connected else ''
            break

    if state.connected and state.device:
        try:
            ip_out = await _run('-t', '-f', 'IP4.ADDRESS',
                                'device', 'show', state.device)
            for line in ip_out.splitlines():
                parts = _split(line)
                if len(parts) >= 2 and parts[1]:
                    state.ip_address = parts[1].split('/')[0]
                    break
        except NotAvailableError:
            pass

        for net in await scan(rescan=False):
            if net.in_use:
                state.signal = net.signal
                break

    return state


async def set_enabled(on: bool) -> WifiState:
    """Turn the wifi radio on or off."""
    await _run('radio', 'wifi', 'on' if on else 'off')
    await asyncio.sleep(0.5)
    return await status()


async def toggle() -> WifiState:
    current = await status()
    return await set_enabled(not current.enabled)


async def connect(ssid: str, password: str | None = None,
                  timeout: float = 45.0) -> WifiState:
    """
    Join a network.

    With no password, tries an existing saved profile first -- that
    covers both open networks and ones already configured. Only pass a
    password for a network being joined the first time.
    """
    if password is None:
        if ssid in await saved_networks():
            await _run('connection', 'up', ssid, timeout=timeout)
            return await status()
        await _run('device', 'wifi', 'connect', ssid, timeout=timeout)
        return await status()

    await _run('device', 'wifi', 'connect', ssid,
               'password', password, timeout=timeout)
    return await status()


async def disconnect() -> WifiState:
    current = await status()
    if current.device:
        await _run('device', 'disconnect', current.device)
    return await status()


async def forget(ssid: str) -> None:
    """Delete a saved profile."""
    if ssid not in await saved_networks():
        raise NotFoundError('saved network', ssid,
                            await saved_networks())
    await _run('connection', 'delete', ssid)
