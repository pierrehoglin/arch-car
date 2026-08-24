"""
HFP call control.

Ordering matters: bluetooth -> ofono -> wireplumber. If a modem shows up
with an empty `interfaces` list, the HFP link never established -- see
HFP_SERVICE_ORDERING.md.
"""

from dataclasses import dataclass, asdict
from typing import AsyncIterator

from carlib.dbus import ofono
from carlib.core.errors import NotAvailableError
from carlib.core.match import select_optional
from carlib.dbus.ofono import ModemInfo
from carlib.dbus.variants import props


@dataclass
class Call:
    path: str
    state: str = ''
    number: str = ''
    name: str = ''
    start_time: str = ''
    multiparty: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def who(self) -> str:
        return self.name or self.number or 'unknown'

    @property
    def incoming(self) -> bool:
        return self.state in ('incoming', 'waiting')

    @classmethod
    def from_props(cls, path: str, raw: dict) -> 'Call':
        p = props(raw)
        return cls(
            path=path,
            state=p.get('State', ''),
            number=p.get('LineIdentification', ''),
            name=p.get('Name', ''),
            start_time=p.get('StartTime', ''),
            multiparty=bool(p.get('Multiparty', False)),
        )


@dataclass
class NetworkInfo:
    operator: str = ''
    status: str = ''
    strength: int | None = None
    technology: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HandsfreeInfo:
    features: list[str]
    voice_recognition: bool = False
    battery: int | None = None
    inband_ringing: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VolumeInfo:
    speaker: int | None = None
    microphone: int | None = None
    muted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


async def modems() -> list[ModemInfo]:
    return await ofono.modems()


async def resolve(match: str | None = None) -> ModemInfo:
    """Pick a modem by MAC, path fragment or name."""
    return select_optional(
        await modems(), match,
        what='modem',
        keys=lambda m: (m.path, m.serial, m.name),
        label=lambda m: m.name,
    )


async def _ready(match: str | None) -> ModemInfo:
    """Resolve a modem and insist it can actually place calls."""
    modem = await resolve(match)
    if not modem.ready:
        raise NotAvailableError(
            f'{modem.name} has no VoiceCallManager interface',
            hint='the HFP link is not up. Run `online` first, and if that '
                 'fails restart in order: bluetooth, ofono, wireplumber.')
    return modem


async def online(match: str | None = None) -> ModemInfo:
    """
    Power up and bring a modem online.

    Interfaces only appear once it is online, so callers should use the
    returned value rather than a previously fetched one.
    """
    modem = await resolve(match)
    proxy = ofono.modem_proxy(modem.path)

    if not modem.powered:
        await proxy.set_property('Powered', ('b', True))
    if not modem.online:
        await proxy.set_property('Online', ('b', True))

    p = props(await proxy.get_properties())
    modem.powered = bool(p.get('Powered', False))
    modem.online = bool(p.get('Online', False))
    modem.interfaces = list(p.get('Interfaces') or [])
    return modem


async def dial(number: str, match: str | None = None,
               hide_callerid: bool = False) -> Call:
    modem = await _ready(match)
    vcm = ofono.calls_proxy(modem.path)

    path = await vcm.dial(number,
                          'enabled' if hide_callerid else 'default')
    call = ofono.call_proxy(path)
    return Call.from_props(path, await call.get_properties())


async def active(match: str | None = None) -> list[Call]:
    modem = await _ready(match)
    vcm = ofono.calls_proxy(modem.path)
    return [Call.from_props(p, raw) for p, raw in await vcm.get_calls()]


async def answer(match: str | None = None) -> None:
    modem = await _ready(match)
    await ofono.calls_proxy(modem.path).answer()


async def hangup(match: str | None = None,
                 call_path: str | None = None) -> None:
    """Hang up one call, or all of them when no path is given."""
    if call_path:
        await ofono.call_proxy(call_path).hangup()
        return
    modem = await _ready(match)
    await ofono.calls_proxy(modem.path).hangup_all()


async def call_state(call_path: str) -> Call | None:
    """
    Re-read one call, or None once it is gone.

    oFono destroys the object when the call ends, so a failed read is
    the normal end-of-call signal rather than an error.
    """
    try:
        proxy = ofono.call_proxy(call_path)
        return Call.from_props(call_path, await proxy.get_properties())
    except Exception:
        return None


async def watch(match: str | None = None
                ) -> AsyncIterator[tuple[str, Call | str]]:
    """
    Yield ('added', Call) and ('removed', path) as calls come and go.

    This is what an incoming-call popup should consume.
    """
    modem = await _ready(match)
    vcm = ofono.calls_proxy(modem.path)

    async for path, raw in vcm.call_added:
        yield 'added', Call.from_props(path, raw)


async def watch_removed(match: str | None = None) -> AsyncIterator[str]:
    modem = await _ready(match)
    vcm = ofono.calls_proxy(modem.path)
    async for path in vcm.call_removed:
        yield path


async def network(match: str | None = None) -> NetworkInfo:
    modem = await resolve(match)
    p = props(await ofono.network_proxy(modem.path).get_properties())
    return NetworkInfo(
        operator=p.get('Name', ''),
        status=p.get('Status', ''),
        strength=p.get('Strength'),
        technology=p.get('Technology', ''),
    )


async def handsfree(match: str | None = None) -> HandsfreeInfo:
    modem = await resolve(match)
    p = props(await ofono.handsfree_proxy(modem.path).get_properties())
    return HandsfreeInfo(
        features=list(p.get('Features') or []),
        voice_recognition=bool(p.get('VoiceRecognition', False)),
        battery=p.get('BatteryChargeLevel'),
        inband_ringing=bool(p.get('InbandRinging', False)),
    )


async def set_voice_recognition(enabled: bool,
                                match: str | None = None) -> bool:
    """Trigger the phone's own assistant over HFP."""
    modem = await resolve(match)
    proxy = ofono.handsfree_proxy(modem.path)
    await proxy.set_property('VoiceRecognition', ('b', enabled))
    p = props(await proxy.get_properties())
    return bool(p.get('VoiceRecognition', False))


async def send_tones(tones: str, match: str | None = None) -> None:
    """DTMF digits during a call, for phone menus."""
    modem = await resolve(match)
    await ofono.handsfree_proxy(modem.path).send_tones(tones)


async def volume(match: str | None = None,
                 speaker: int | None = None,
                 microphone: int | None = None,
                 muted: bool | None = None) -> VolumeInfo:
    """
    Read or adjust call audio. Pass nothing to just read.

    Levels are bytes ('y'), not ints -- sending 'i' is rejected.
    """
    modem = await resolve(match)
    proxy = ofono.volume_proxy(modem.path)

    if speaker is not None:
        await proxy.set_property(
            'SpeakerVolume', ('y', max(0, min(100, speaker))))
    if microphone is not None:
        await proxy.set_property(
            'MicrophoneVolume', ('y', max(0, min(100, microphone))))
    if muted is not None:
        await proxy.set_property('Muted', ('b', muted))

    p = props(await proxy.get_properties())
    return VolumeInfo(
        speaker=p.get('SpeakerVolume'),
        microphone=p.get('MicrophoneVolume'),
        muted=bool(p.get('Muted', False)),
    )
