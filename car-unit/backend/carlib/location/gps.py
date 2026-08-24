"""
GPS and location via ModemManager.

Two useful sources on a SIM7600:

    gps-raw    ModemManager parses the fix for you: lat, lon, altitude
    gps-nmea   the raw sentences, which carry satellite counts, HDOP,
               speed and heading that gps-raw drops

This module reads both and merges them, because neither alone gives a
complete picture. NMEA parsing is pure and testable; everything else
goes through D-Bus.

A cold start takes minutes. `$GPGSA,A,1,` means no fix yet -- the 1 is
the fix mode, and 2 or 3 means you have one.
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date as date_type
from typing import AsyncIterator

from carlib.dbus import modemmanager as mm
from carlib.core.errors import NotAvailableError
from carlib.core.match import select_optional
from carlib.dbus.variants import unwrap

KNOTS_TO_KMH = 1.852

FIX_QUALITY = {
    0: 'invalid',
    1: 'gps',
    2: 'dgps',
    3: 'pps',
    4: 'rtk-fixed',
    5: 'rtk-float',
    6: 'estimated',
    7: 'manual',
    8: 'simulation',
}

FIX_MODE = {1: 'none', 2: '2d', 3: '3d'}


@dataclass
class Satellite:
    prn: int
    elevation: int | None = None
    azimuth: int | None = None
    snr: int | None = None

    @property
    def used(self) -> bool:
        """Set by the caller from GSA; GSV alone does not say."""
        return getattr(self, '_used', False)


@dataclass
class Fix:
    """A position fix, merged from gps-raw and NMEA."""

    has_fix: bool = False
    mode: str = 'none'              # none / 2d / 3d
    quality: str = 'invalid'

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None   # metres above mean sea level

    speed_kmh: float | None = None
    heading: float | None = None    # degrees true

    satellites_used: int = 0
    satellites_visible: int = 0
    hdop: float | None = None
    pdop: float | None = None
    vdop: float | None = None

    utc: str | None = None          # ISO 8601
    satellites: list[Satellite] = field(default_factory=list)

    # Coarse fallback when GPS has no fix yet.
    cell_mcc: str = ''
    cell_mnc: str = ''
    cell_lac: str = ''
    cell_id: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def coordinates(self) -> tuple[float, float] | None:
        if self.latitude is None or self.longitude is None:
            return None
        return (self.latitude, self.longitude)

    @property
    def maps_url(self) -> str | None:
        c = self.coordinates
        if c is None:
            return None
        return f'https://www.openstreetmap.org/?mlat={c[0]}&mlon={c[1]}#map=17'

    def format_coordinates(self) -> str:
        """Degrees and decimal minutes, as marine and aviation use."""
        c = self.coordinates
        if c is None:
            return 'no fix'
        lat, lon = c
        ns = 'N' if lat >= 0 else 'S'
        ew = 'E' if lon >= 0 else 'W'
        lat, lon = abs(lat), abs(lon)
        return (f'{int(lat)}deg {(lat % 1) * 60:06.3f}\' {ns}  '
                f'{int(lon)}deg {(lon % 1) * 60:06.3f}\' {ew}')


# --- NMEA parsing ----------------------------------------------------------

def _checksum_ok(sentence: str) -> bool:
    """NMEA checksum is an XOR of everything between $ and *."""
    if '*' not in sentence:
        return False
    body, _, checksum = sentence[1:].partition('*')
    try:
        expected = int(checksum[:2], 16)
    except ValueError:
        return False
    actual = 0
    for ch in body:
        actual ^= ord(ch)
    return actual == expected


def _coord(value: str, hemisphere: str) -> float | None:
    """
    NMEA packs coordinates as ddmm.mmmm / dddmm.mmmm.

    Degrees are everything before the last two digits of the integer
    part; the rest is minutes.
    """
    if not value or not hemisphere:
        return None
    try:
        dot = value.index('.')
    except ValueError:
        if len(value) < 3:
            return None
        dot = len(value)

    degrees = float(value[:dot - 2])
    minutes = float(value[dot - 2:])
    result = degrees + minutes / 60.0

    if hemisphere.upper() in ('S', 'W'):
        result = -result
    return result


def _float(value: str) -> float | None:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _int(value: str) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _timestamp(time_str: str, date_str: str = '') -> str | None:
    """
    NMEA time is hhmmss.sss and date is ddmmyy, in separate sentences.

    Returns ISO 8601 UTC, or None when either is missing.
    """
    if not time_str:
        return None

    match = re.match(r'^(\d{2})(\d{2})(\d{2})(\.\d+)?$', time_str)
    if not match:
        return None
    hh, mm_, ss = int(match.group(1)), int(match.group(2)), int(match.group(3))

    if date_str and re.match(r'^\d{6}$', date_str):
        dd = int(date_str[0:2])
        mo = int(date_str[2:4])
        yy = 2000 + int(date_str[4:6])
        try:
            dt = datetime(yy, mo, dd, hh, mm_, ss, tzinfo=timezone.utc)
        except ValueError:
            return None
    else:
        today = date_type.today()
        try:
            dt = datetime(today.year, today.month, today.day,
                          hh, mm_, ss, tzinfo=timezone.utc)
        except ValueError:
            return None

    return dt.isoformat()


def parse_nmea(text: str) -> Fix:
    """
    Parse a block of NMEA sentences into a single Fix.

    Handles the talker-ID variation the SIM7600 emits: GP for GPS, GN
    for mixed GNSS, BD for BeiDou, GL for GLONASS.
    """
    fix = Fix()
    used_prns: set[int] = set()
    seen: dict[int, Satellite] = {}
    time_str = ''
    date_str = ''

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('$'):
            continue
        # Tolerate a missing or bad checksum: a truncated sentence still
        # carries useful fields, and dropping it loses the whole fix.
        body = line.split('*')[0]
        parts = body.split(',')
        if not parts:
            continue

        talker = parts[0][1:]
        kind = talker[-3:] if len(talker) >= 3 else talker

        if kind == 'GGA' and len(parts) >= 10:
            time_str = parts[1] or time_str
            lat = _coord(parts[2], parts[3])
            lon = _coord(parts[4], parts[5])
            quality = _int(parts[6]) or 0
            fix.quality = FIX_QUALITY.get(quality, 'invalid')
            if quality > 0 and lat is not None and lon is not None:
                fix.latitude = lat
                fix.longitude = lon
                fix.has_fix = True
            sats = _int(parts[7])
            if sats:
                fix.satellites_used = sats
            fix.hdop = _float(parts[8]) or fix.hdop
            alt = _float(parts[9])
            if alt is not None:
                fix.altitude = alt

        elif kind == 'RMC' and len(parts) >= 10:
            time_str = parts[1] or time_str
            status = parts[2]
            lat = _coord(parts[3], parts[4])
            lon = _coord(parts[5], parts[6])
            if status == 'A' and lat is not None and lon is not None:
                fix.latitude = lat
                fix.longitude = lon
                fix.has_fix = True
            knots = _float(parts[7])
            if knots is not None:
                fix.speed_kmh = round(knots * KNOTS_TO_KMH, 2)
            heading = _float(parts[8])
            if heading is not None:
                fix.heading = heading
            date_str = parts[9] or date_str

        elif kind == 'GSA' and len(parts) >= 18:
            mode = _int(parts[2]) or 1
            # Several constellations each emit a GSA; keep the best.
            if FIX_MODE.get(mode, 'none') != 'none' or fix.mode == 'none':
                if mode >= 2 or fix.mode == 'none':
                    fix.mode = FIX_MODE.get(mode, 'none')
            for prn_field in parts[3:15]:
                prn = _int(prn_field)
                if prn:
                    used_prns.add(prn)
            fix.pdop = _float(parts[15]) or fix.pdop
            fix.hdop = _float(parts[16]) or fix.hdop
            fix.vdop = _float(parts[17]) or fix.vdop

        elif kind == 'GSV' and len(parts) >= 4:
            total = _int(parts[3])
            if total:
                fix.satellites_visible = max(fix.satellites_visible, total)
            # Satellites come in groups of four fields.
            for i in range(4, len(parts) - 3, 4):
                prn = _int(parts[i])
                if not prn:
                    continue
                seen[prn] = Satellite(
                    prn=prn,
                    elevation=_int(parts[i + 1]),
                    azimuth=_int(parts[i + 2]),
                    snr=_int(parts[i + 3]),
                )

    if used_prns and not fix.satellites_used:
        fix.satellites_used = len(used_prns)

    for prn, sat in seen.items():
        setattr(sat, '_used', prn in used_prns)
    fix.satellites = sorted(seen.values(), key=lambda s: s.prn)

    fix.utc = _timestamp(time_str, date_str)

    if fix.mode == 'none' and fix.has_fix:
        fix.mode = '3d' if fix.altitude is not None else '2d'

    return fix


# --- Modem selection -------------------------------------------------------

async def modems() -> list[mm.ModemInfo]:
    return await mm.modems()


async def resolve(match: str | None = None) -> mm.ModemInfo:
    """Pick a modem by path fragment or model name."""
    return select_optional(
        await mm.modems(), match,
        what='modem',
        keys=lambda m: (m.path, m.model, m.manufacturer),
        label=lambda m: m.model or m.path,
    )


# --- Operations ------------------------------------------------------------

async def enable(match: str | None = None,
                 nmea: bool = True,
                 raw: bool = True,
                 assisted: bool = False,
                 signal_changes: bool = True) -> mm.ModemInfo:
    """
    Turn on location gathering.

    signal_changes makes ModemManager emit PropertiesChanged as the fix
    updates, which is what `watch()` needs -- without it you can only
    poll.
    """
    modem = await resolve(match)
    proxy = mm.location_proxy(modem.path)

    caps = await proxy.capabilities

    sources = mm.SOURCE_3GPP_LAC_CI & caps
    if nmea:
        sources |= mm.SOURCE_GPS_NMEA & caps
    if raw:
        sources |= mm.SOURCE_GPS_RAW & caps
    if assisted:
        sources |= (mm.SOURCE_AGPS_MSB | mm.SOURCE_AGPS_MSA) & caps

    if not sources:
        raise NotAvailableError(
            'this modem reports no usable location sources',
            hint=f'capabilities: {mm.decode_sources(caps) or "none"}')

    await proxy.setup(sources, signal_changes)

    modem.location_enabled = mm.decode_sources(await proxy.enabled)
    return modem


async def disable(match: str | None = None) -> None:
    modem = await resolve(match)
    await mm.location_proxy(modem.path).setup(mm.SOURCE_NONE, False)


async def set_refresh_rate(seconds: int, match: str | None = None) -> int:
    """
    How often ModemManager re-reads the GPS. Default is 30s, which is
    far too slow for a moving vehicle -- 1 or 2 is more useful.
    """
    modem = await resolve(match)
    proxy = mm.location_proxy(modem.path)
    await proxy.set_gps_refresh_rate(seconds)
    return await proxy.gps_refresh_rate


async def set_supl_server(server: str, match: str | None = None) -> None:
    """
    Point A-GPS at a SUPL server to shorten time-to-first-fix.

    supl.google.com:7275 is the usual choice. Needs a working data
    connection.
    """
    modem = await resolve(match)
    await mm.location_proxy(modem.path).set_supl_server(server)


def _merge(raw_location: dict) -> Fix:
    """
    Build a Fix from a GetLocation reply.

    Keys are MMModemLocationSource values. NMEA gives the richer
    picture, so parse that first and let gps-raw fill any gaps.
    """
    sources = {k: unwrap(v) for k, v in (raw_location or {}).items()}

    nmea_text = sources.get(mm.SOURCE_GPS_NMEA)
    fix = parse_nmea(nmea_text) if isinstance(nmea_text, str) else Fix()

    gps_raw = sources.get(mm.SOURCE_GPS_RAW)
    if isinstance(gps_raw, dict):
        p = {k: unwrap(v) for k, v in gps_raw.items()}
        if fix.latitude is None and p.get('latitude') is not None:
            fix.latitude = float(p['latitude'])
            fix.longitude = float(p['longitude'])
            fix.has_fix = True
        if fix.altitude is None and p.get('altitude') is not None:
            fix.altitude = float(p['altitude'])
        if fix.utc is None and p.get('utc-time'):
            fix.utc = str(p['utc-time'])

    cell = sources.get(mm.SOURCE_3GPP_LAC_CI)
    if isinstance(cell, str) and cell:
        # Format is MCC,MNC,LAC,CI
        bits = cell.split(',')
        if len(bits) >= 4:
            fix.cell_mcc, fix.cell_mnc, fix.cell_lac, fix.cell_id = bits[:4]

    # gps-raw alone carries no GSA sentence, so infer the mode from
    # whether an altitude came through.
    if fix.has_fix and fix.mode == 'none':
        fix.mode = '3d' if fix.altitude is not None else '2d'

    return fix


async def get(match: str | None = None) -> Fix:
    """Read the current position."""
    modem = await resolve(match)
    proxy = mm.location_proxy(modem.path)

    try:
        raw = await proxy.get_location()
    except Exception as exc:
        raise NotAvailableError(
            f'cannot read location: {exc}',
            hint='location gathering may not be enabled -- run `enable` '
                 'first. If this is a polkit error, add a rule for '
                 'org.freedesktop.ModemManager1.') from exc

    return _merge(raw)


async def status(match: str | None = None) -> dict:
    """Capabilities and current settings, for diagnosis."""
    modem = await resolve(match)
    proxy = mm.location_proxy(modem.path)

    return {
        'modem': modem.to_dict(),
        'capabilities': mm.decode_sources(await proxy.capabilities),
        'enabled': mm.decode_sources(await proxy.enabled),
        'refresh_rate': await proxy.gps_refresh_rate,
        'signals_location': await proxy.signals_location,
        'supl_server': await proxy.supl_server,
    }


async def watch(match: str | None = None) -> AsyncIterator[Fix]:
    """
    Yield a Fix whenever the position updates.

    Requires signal_changes=True at enable time, otherwise ModemManager
    never emits and this blocks forever.

        async for fix in location.watch():
            ...
    """
    modem = await resolve(match)
    proxy = mm.location_proxy(modem.path)

    if not await proxy.signals_location:
        raise NotAvailableError(
            'this modem is not signalling location changes',
            hint='re-run enable with signal_changes=True')

    async for iface, changed, _invalidated in proxy.properties_changed:
        if iface != mm.IFACE_LOCATION:
            continue
        if 'Location' not in changed:
            continue
        yield _merge(unwrap(changed['Location']))
