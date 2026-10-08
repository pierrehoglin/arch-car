"""
Phone calls, as the screens see them.

calls.py drives oFono one request at a time; this is the daemon's
long-running view of every connected phone's calls: what is ringing,
what is connected, who it is, and how each one ended. Every change is
published as the 'call' event, and every request a screen makes goes
through here and answers only once the phone has accepted or refused
it. What happens after that -- the other end picking up, hanging up,
a call coming in -- arrives through the event alone.

Several phones can be connected at once -- two people in the car is
the ordinary case -- and each has its own hands-free link, followed
separately. Every call says which phone it is on, and call ids are
unique across phones, so a request about a call needs only its id.
Dialling names the phone instead. Either can be left out when there
is only one candidate; when there is more than one, the request is
refused as ambiguous rather than guessed at.

Muting is the car's own microphone, not the phone's: hands-free has
no mute command for the car to send (oFono answers NotImplemented),
and there is one microphone, so one mute covers every call going. It
is lifted when the last call ends, so the next one never starts
muted with nobody here knowing why.

The 'call' event:

    {
      "available": true,            any phone with a hands-free link
      "phones": [{
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "Pixel 8",
        "muted": false              the car's microphone, while this
                                    phone has a call
      }],
      "calls": [{
        "id": "AABBCCDDEEFF-3",
        "phone": "AA:BB:CC:DD:EE:FF",
        "state": "incoming",        incoming dialing alerting active
                                    held waiting ended
        "direction": "in",          in | out
        "number": "+46701234567",
        "name": "Anna",             from that phone's book, or ""
        "photo": "<digest>",        for /phonebook/photo/<digest>, or ""
        "connected_at": 1791360000, unix seconds, once active
        "ended_reason": ""          local | remote | network, once ended
      }]
    }

An ended call stays in the list as "ended" for ENDED_SECONDS, so the
screens can say so, then goes.

While any call is going, on any phone, every audio source is paused,
and what was playing comes back when the last one ends -- see
source.hold_for_call.
"""

import asyncio
import contextlib
import logging
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Callable

from carlib.core.errors import CarError, NotAvailableError
from carlib.dbus import ofono
from carlib.dbus.variants import props
from carlib.system import audio

log = logging.getLogger('carlib')

# How long an ended call is still shown as ended.
ENDED_SECONDS = 4.0

# Between looks for phones, and checks on the ones already followed.
CHECK_SECONDS = 2.0

# oFono's call states, and which of them mean ringing here.
INCOMING = ('incoming', 'waiting')
LIVE = ('active', 'held', 'dialing', 'alerting', 'incoming', 'waiting')


class CallFailed(CarError):
    """
    A request the phone could not carry out, in a form a screen can
    act on. Each reason its own status:

        no_phone        409  no phone with a hands-free link, or not
                             the one named
        choose_phone    409  more than one phone, and none named
        no_call         409  nothing to answer, end or hold
        choose_call     409  more than one call it could be, and none
                             named
        invalid_number  422  the phone rejected the number's format
        refused         502  the phone said no -- no signal, flight
                             mode, or a call it would not place
    """

    STATUSES = {'no_phone': 409, 'choose_phone': 409, 'no_call': 409,
                'choose_call': 409, 'invalid_number': 422, 'refused': 502}

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.status = self.STATUSES.get(reason, 400)
        super().__init__(message)


def _refusal(exc: Exception, doing: str) -> CallFailed:
    """oFono's D-Bus error as a CallFailed."""
    name = str(getattr(exc, 'dbus_error_name', '') or '')
    text = str(exc).strip() or name
    if name.endswith('InvalidFormat') or 'InvalidFormat' in text:
        return CallFailed('invalid_number', f'not a number the phone '
                          f'can call: {text}')
    return CallFailed('refused', f'the phone would not {doing}: {text}')


def _address(modem: ofono.ModemInfo) -> str:
    """The phone's Bluetooth address: oFono's HFP modems carry it as
    the serial, and in the path."""
    if re.fullmatch(r'([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', modem.serial or ''):
        return modem.serial.upper()
    match = re.search(r'dev_([0-9A-Fa-f_]{17})', modem.path)
    return match.group(1).replace('_', ':').upper() if match else modem.path


def _call_id(address: str, path: str) -> str:
    """'AA:BB:…' and '…/voicecall03' -> 'AABB…-3': short, and unique
    across phones, which number their calls from 1 each."""
    match = re.search(r'(\d+)$', path)
    number = str(int(match.group(1))) if match else path.rsplit('/', 1)[-1]
    return f"{address.replace(':', '')}-{number}"


@dataclass
class Call:
    path: str
    id: str
    phone: str
    state: str
    direction: str
    number: str = ''
    name: str = ''
    photo: str = ''
    connected_at: float | None = None
    ended_reason: str = ''

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop('path')
        if data['connected_at'] is not None:
            data['connected_at'] = round(data['connected_at'], 1)
        return data

    @property
    def live(self) -> bool:
        return self.state != 'ended'


@dataclass
class Line:
    """One phone's hands-free link, and what is listening to it."""

    modem: ofono.ModemInfo
    address: str
    muted: bool = False
    tasks: list[asyncio.Task] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.modem.name


class Caller:
    """Who a number is, from a phone's own cached books."""

    def __init__(self) -> None:
        self._books: dict[str, tuple[float, dict[str, tuple[str, str]]]] = {}

    def lookup(self, address: str, number: str) -> tuple[str, str]:
        digits = re.sub(r'\D', '', number or '')
        if len(digits) < 7 or not address:
            return '', ''
        loaded, index = self._books.get(address, (0.0, {}))
        # Reloaded now and then, for a book synced since -- cheap, it
        # is a JSON file.
        if time.time() - loaded > 60:
            index = self._load(address)
            self._books[address] = (time.time(), index)
        return index.get(digits[-7:], ('', ''))

    @staticmethod
    def _load(address: str) -> dict[str, tuple[str, str]]:
        from carlib.bluetooth import contacts
        index: dict[str, tuple[str, str]] = {}
        # Favourites last, so their entry -- often the one with the
        # photo -- wins for a number in both.
        for book in ('pb', 'fav'):
            try:
                cached = contacts.load(address, book)
            except Exception:
                continue
            for contact in cached.contacts:
                if not contact.name:
                    continue
                for entry in contact.numbers:
                    digits = re.sub(r'\D', '', entry.number)
                    if len(digits) >= 7:
                        index[digits[-7:]] = (contact.name, contact.photo)
        return index


class Watcher:
    def __init__(self) -> None:
        self.on_change: Callable[[dict], None] | None = None
        # By modem path.
        self.lines: dict[str, Line] = {}
        # By call path.
        self.calls: dict[str, Call] = {}
        self._caller = Caller()
        self._published: dict | None = None
        self._call_tasks: dict[str, list[asyncio.Task]] = {}
        self._reasons: dict[str, str] = {}
        self._holding = False
        # Whether this muted the microphone, for the call going.
        self._mic_muted = False
        # Set when the music may need pausing or resuming; acted on by
        # a task of its own -- see _music_loop.
        self._music_wanted = asyncio.Event()
        self._wake = asyncio.Event()

    # --- What the screens get ------------------------------------------

    def payload(self) -> dict:
        lines = sorted(self.lines.values(), key=lambda line: line.name.lower())
        return {
            'available': bool(self.lines),
            'phones': [{'address': line.address, 'name': line.name,
                        'muted': line.muted} for line in lines],
            'calls': [c.to_dict() for c in sorted(
                self.calls.values(), key=lambda c: (c.phone, c.path))],
        }

    def _publish(self) -> None:
        data = self.payload()
        if data == self._published:
            return
        self._published = data
        if self.on_change:
            try:
                self.on_change(data)
            except Exception:
                log.exception('calls: publishing failed')

    # --- Following the phones ------------------------------------------

    async def run(self) -> None:
        """Forever: follow every phone with a hands-free link, take up
        new ones, let go of ones that have gone."""
        music = asyncio.create_task(self._music_loop())
        try:
            while True:
                try:
                    await self._survey()
                except Exception:
                    log.exception('calls: watching failed')
                await self._sleep(CHECK_SECONDS)
        finally:
            music.cancel()
            for path in list(self.lines):
                self._drop(path, quiet=True)

    async def _sleep(self, seconds: float) -> None:
        """A pause a request can cut short, so its effect is read at
        once rather than at the next check."""
        self._wake.clear()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._wake.wait(), seconds)

    async def _survey(self) -> None:
        found = await self._phones()

        ready = {}
        for modem in found:
            if not modem.ready and modem.powered and not modem.online:
                # Connected -- powered is oFono's word for it -- but not
                # online yet, so no call interfaces. Online asks for
                # nothing over the air. Never Powered: for oFono that is
                # "connect to this phone", and setting it for every
                # paired phone it knows reconnected a phone somebody had
                # just disconnected, every two seconds.
                with contextlib.suppress(Exception):
                    proxy = ofono.modem_proxy(modem.path)
                    await proxy.set_property('Online', ('b', True))
                    p = props(await proxy.get_properties())
                    modem.online = bool(p.get('Online', False))
                    modem.interfaces = list(p.get('Interfaces') or [])
            if modem.ready:
                ready[modem.path] = modem

        for path in list(self.lines):
            if path not in ready:
                self._drop(path)
        for path, modem in ready.items():
            if path not in self.lines:
                self._take(modem)

        for path in list(self.lines):
            await self._reconcile(path)
        await self._after_change()

    async def _phones(self) -> list[ofono.ModemInfo]:
        """
        oFono's phones -- only while Bluetooth is running.

        Checked first, as the pairing watcher does: asking oFono
        anything starts it on demand when it is stopped, and oFono pulls
        Bluetooth up with it (Wants=bluetooth.service, so HFP registers
        in the right order). Turning Bluetooth off then lasted until
        the next survey, two seconds later.
        """
        from carlib.system import bluetooth, services
        try:
            if not (await services.status(bluetooth.SERVICE)).active:
                return []
        except Exception:
            return []
        try:
            found = await ofono.modems()
        except NotAvailableError:
            return []
        return [m for m in found if m.type == 'hfp'] or found

    def _take(self, modem: ofono.ModemInfo) -> None:
        line = Line(modem=modem, address=_address(modem))
        vcm = ofono.calls_proxy(modem.path)
        line.tasks = [
            asyncio.create_task(self._on_added(line, vcm)),
            asyncio.create_task(self._on_removed(vcm)),
        ]
        self.lines[modem.path] = line
        log.info('calls: following %s', line.name)

    def _drop(self, path: str, quiet: bool = False) -> None:
        """A phone gone. Its calls are over as far as anyone here can
        tell."""
        line = self.lines.pop(path, None)
        if line is None:
            return
        if not quiet:
            log.info('calls: %s has gone', line.name)
        for task in line.tasks:
            task.cancel()
        for call_path, call in list(self.calls.items()):
            if call.phone == line.address:
                for task in self._call_tasks.pop(call_path, []):
                    task.cancel()
                del self.calls[call_path]

    def _line_of(self, call: Call) -> Line | None:
        return next((line for line in self.lines.values()
                     if line.address == call.phone), None)

    async def _on_added(self, line: Line, vcm) -> None:
        async for path, raw in vcm.call_added:
            self._update(line, path, props(raw))
            await self._after_change()

    async def _on_removed(self, vcm) -> None:
        async for path in vcm.call_removed:
            self._ended(path)
            await self._after_change()

    def _listen(self, line: Line, path: str) -> None:
        if path in self._call_tasks:
            return
        proxy = ofono.call_proxy(path)

        async def changes() -> None:
            async for name, value in proxy.property_changed:
                raw = value[1] if isinstance(value, tuple) else value
                self._update(line, path, {name: raw})
                await self._after_change()
                # Over once the call is: it ends this loop itself
                # rather than being cancelled by _ended, which runs in
                # it when the state goes to disconnected.
                call = self.calls.get(path)
                if call is None or not call.live:
                    return

        async def reasons() -> None:
            async for reason in proxy.disconnect_reason:
                self._reasons[path] = reason

        self._call_tasks[path] = [asyncio.create_task(changes()),
                                  asyncio.create_task(reasons())]

    async def _reconcile(self, modem_path: str) -> None:
        """Read one phone's calls afresh. Signals are the fast path;
        this is the one that cannot miss anything, and the one that
        notices a phone going."""
        line = self.lines.get(modem_path)
        if line is None:
            return
        try:
            listed = await ofono.calls_proxy(modem_path).get_calls()
        except Exception:
            # The hands-free link has gone with the phone.
            self._drop(modem_path)
            return
        seen = set()
        for path, raw in listed:
            seen.add(path)
            self._update(line, path, props(raw))
        for path, call in list(self.calls.items()):
            if call.phone == line.address and path not in seen and call.live:
                self._ended(path)

    def _update(self, line: Line, path: str, changes: dict) -> None:
        call = self.calls.get(path)
        state = str(changes.get('State', call.state if call else ''))
        if call is None:
            if state not in LIVE:
                return
            call = Call(path=path, id=_call_id(line.address, path),
                        phone=line.address, state=state,
                        direction='in' if state in INCOMING else 'out')
            self.calls[path] = call
            self._listen(line, path)
        if not call.live:
            return
        if 'LineIdentification' in changes:
            call.number = str(changes['LineIdentification'] or '')
        if changes.get('Name'):
            call.name = str(changes['Name'])
        if state == 'disconnected':
            self._ended(path)
            return
        call.state = state
        if state == 'active' and call.connected_at is None:
            call.connected_at = time.time()
        # That phone's own book: the same number can be a different
        # person in each. Its name over the network's, which is often
        # blank or a bare number.
        name, photo = self._caller.lookup(line.address, call.number)
        if name:
            call.name = name
        call.photo = photo

    def _ended(self, path: str) -> None:
        call = self.calls.get(path)
        # Not the task this is running in: the call's own listener
        # calls this when the state goes to disconnected, and cancelling
        # it here cut short whatever it did next -- resuming the radio,
        # once. It ends its loop by itself instead.
        running = asyncio.current_task()
        for task in self._call_tasks.pop(path, []):
            if task is not running:
                task.cancel()
        if call is None or not call.live:
            return
        call.state = 'ended'
        call.ended_reason = self._reasons.pop(path, '') or 'remote'
        asyncio.get_running_loop().call_later(
            ENDED_SECONDS, self._expire, path)

    def _expire(self, path: str) -> None:
        call = self.calls.get(path)
        if call is not None and not call.live:
            del self.calls[path]
            self._publish()

    async def _after_change(self) -> None:
        """Publish; silence or restore the music as calls begin and
        end; unmute a phone whose calls are over."""
        if self._mic_muted and not any(c.live for c in self.calls.values()):
            # The microphone stays muted in PipeWire after the call; the
            # next call starting muted would have the other end hearing
            # nothing and nobody here knowing why.
            with contextlib.suppress(Exception):
                await audio.set_muted(False, audio.SOURCE)
            self._mic_muted = False
        for line in self.lines.values():
            line.muted = self._mic_muted and any(
                c.live and c.phone == line.address for c in self.calls.values())
        self._publish()
        self._music_wanted.set()

    async def _music_loop(self) -> None:
        """
        Music off while any call is going, back on when none is -- in a
        task of its own, woken by every change.

        Its own task, so nothing can cut it short: the listeners that
        notice calls ending are themselves stopped as calls end, and a
        resume running in one of them was cancelled halfway -- the note
        of what to resume already cleared, the radio not yet on.

        One step at a time, and checked again after each: pausing takes
        a moment -- it reads what is playing first -- and a call can be
        over before it has finished. A busy signal is: dialling, then
        gone, inside a second.
        """
        while True:
            await self._music_wanted.wait()
            self._music_wanted.clear()
            try:
                await self._sync_music()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception('calls: pausing or resuming the music failed')

    async def _sync_music(self) -> None:
        from carlib.system import source
        while True:
            live = any(c.live for c in self.calls.values())
            if live and not self._holding:
                self._holding = True
                try:
                    held = await source.hold_for_call()
                    log.info('calls: paused %s',
                             ', '.join(held) or 'nothing')
                except Exception:
                    log.exception('calls: pausing the music failed')
            elif not live and (self._holding or source.in_call()):
                # The second half also catches music held for a call
                # by anything that went wrong in between: nothing is
                # going, so nothing should be holding it -- the music
                # would stay off, and traffic announcements blocked.
                self._holding = False
                try:
                    resumed = await source.release_after_call()
                    log.info('calls: resumed %s',
                             ', '.join(resumed) or 'nothing')
                except Exception:
                    log.exception('calls: resuming the music failed')
            else:
                return

    # --- Requests --------------------------------------------------------

    def _phone(self, address: str | None) -> Line:
        """The phone named, or the only one there is."""
        if not self.lines:
            raise CallFailed('no_phone', 'no phone with a hands-free '
                             'link is connected')
        if address:
            wanted = address.upper()
            for line in self.lines.values():
                if line.address == wanted:
                    return line
            raise CallFailed('no_phone', f'{address} is not connected '
                             'with a hands-free link')
        if len(self.lines) > 1:
            raise CallFailed('choose_phone', 'more than one phone is '
                             'connected; say which')
        return next(iter(self.lines.values()))

    def _call(self, states: tuple[str, ...], call_id: str | None) -> Call:
        """The call named, or the only one in these states."""
        if not self.lines:
            raise CallFailed('no_phone', 'no phone with a hands-free '
                             'link is connected')
        candidates = [c for c in self.calls.values() if c.state in states]
        if call_id:
            for call in candidates:
                if call.id == call_id:
                    return call
            raise CallFailed('no_call', f'no call {call_id} to do that to')
        if not candidates:
            raise CallFailed('no_call', 'no call to do that to')
        if len(candidates) > 1:
            raise CallFailed('choose_call', 'more than one call it could '
                             'be; say which')
        return candidates[0]

    async def _done(self) -> None:
        """Read the phone's answer into the state straight away, and
        wake the survey so the next check is not long after."""
        self._wake.set()
        for path in list(self.lines):
            await self._reconcile(path)
        await self._after_change()

    async def dial(self, number: str, phone: str | None = None) -> dict:
        line = self._phone(phone)
        number = re.sub(r'[^\d+*#]', '', number or '')
        if not number:
            raise CallFailed('invalid_number', 'no number to call')
        try:
            path = await ofono.calls_proxy(line.modem.path).dial(
                number, 'default')
        except Exception as exc:
            raise _refusal(exc, 'place the call') from exc
        await self._done()
        return {'id': _call_id(line.address, path), 'phone': line.address}

    async def answer(self, call_id: str | None = None) -> dict:
        call = self._call(('incoming',), call_id)
        try:
            await ofono.call_proxy(call.path).answer()
        except Exception as exc:
            raise _refusal(exc, 'answer') from exc
        await self._done()
        return {'id': call.id}

    async def decline(self, call_id: str | None = None) -> dict:
        call = self._call(INCOMING, call_id)
        self._reasons[call.path] = 'local'
        try:
            await ofono.call_proxy(call.path).hangup()
        except Exception as exc:
            raise _refusal(exc, 'decline the call') from exc
        await self._done()
        return {'id': call.id}

    async def hangup(self, call_id: str | None = None) -> dict:
        """One call by its id; with none, every call on every phone --
        the one "end" for a car with a single call going, which is
        nearly always."""
        if call_id:
            call = self._call(LIVE, call_id)
            self._reasons[call.path] = 'local'
            try:
                await ofono.call_proxy(call.path).hangup()
            except Exception as exc:
                raise _refusal(exc, 'end the call') from exc
            await self._done()
            return {'id': call.id}

        live = [c for c in self.calls.values() if c.live]
        if not live:
            raise CallFailed('no_call', 'no call to end')
        for call in live:
            self._reasons[call.path] = 'local'
        for path in {self._line_of(c).modem.path for c in live
                     if self._line_of(c)}:
            try:
                await ofono.calls_proxy(path).hangup_all()
            except Exception as exc:
                raise _refusal(exc, 'end the call') from exc
        await self._done()
        return {'id': None}

    async def hold_and_answer(self, call_id: str | None = None) -> dict:
        """Answer a waiting call, holding the one already going on the
        same phone."""
        call = self._call(('waiting',), call_id)
        line = self._line_of(call)
        if line is None:
            raise CallFailed('no_phone', 'that phone has gone')
        try:
            await ofono.calls_proxy(line.modem.path).hold_and_answer()
        except Exception as exc:
            raise _refusal(exc, 'answer the waiting call') from exc
        await self._done()
        return {'id': call.id}

    async def mute(self, on: bool, phone: str | None = None) -> dict:
        """Mute the car's microphone for the calls going. A phone may
        be named, and must then be one that is connected; with one
        microphone, the mute is the same for all of them."""
        if phone:
            self._phone(phone)
        if not any(c.live for c in self.calls.values()):
            raise CallFailed('no_call', 'no call to mute')
        try:
            await audio.set_muted(bool(on), audio.SOURCE)
        except CarError as exc:
            raise CallFailed('refused', f'the microphone would not '
                             f'{"mute" if on else "unmute"}: {exc}') from exc
        self._mic_muted = bool(on)
        await self._done()
        return {'muted': self._mic_muted}

    async def tones(self, digits: str, call_id: str | None = None) -> dict:
        call = self._call(('active',), call_id)
        line = self._line_of(call)
        if line is None:
            raise CallFailed('no_phone', 'that phone has gone')
        digits = re.sub(r'[^\d*#ABCD]', '', (digits or '').upper())
        if not digits:
            raise CallFailed('invalid_number', 'no digits to send')
        try:
            await ofono.calls_proxy(line.modem.path).send_tones(digits)
        except Exception as exc:
            raise _refusal(exc, 'send the tones') from exc
        return {'id': call.id, 'sent': digits}


# The one the daemon keeps.
current = Watcher()
