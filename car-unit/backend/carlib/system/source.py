"""
Audio source coordination.

A car head unit has one source at a time: radio, or Spotify, or the
phone over Bluetooth. PipeWire will happily mix them all, which is not
what anyone wants, so something has to arbitrate.

MPRIS is the common handle. spotifyd, browsers and Bluetooth A2DP all
expose it, and `playerctl` drives it. FM is the exception -- it is a
raw rtl_fm pipeline with no MPRIS interface -- so it is handled
directly through carlib.radio.fm.

FM is paused rather than stopped when another source takes over.
Pausing the radio mutes it while the receiver keeps running: RDS is
only decodable while tuned, so stopping the pipeline would mean no
traffic announcements. The cost is about 8% of one Pi 4 core,
measured, which is worth paying to avoid a 1.5 second gap at the start
of every announcement.

Two ways to use this:

    select('fm')        explicit switch; pauses everything else
    supervise()         watch for a source starting on its own and
                        stop the others

The supervisor exists because Spotify starts remotely. spotifyd is a
Spotify Connect endpoint, so playback begins when you pick the car
from your phone -- nothing calls into carlib at all. Polling MPRIS is
the only way to notice.

Requires:
    pacman -S playerctl
"""

import time
import asyncio
from dataclasses import dataclass, field, asdict
from typing import AsyncIterator

from carlib.core import settings, state
from carlib.core.errors import NotAvailableError, NotFoundError

PLAYERCTL = 'playerctl'

# The pseudo-source for our own radio pipeline, which has no MPRIS
# interface to find.
FM = 'fm'

# playerctl reports these; only the first means audio is coming out.
PLAYING = 'Playing'

POLL_INTERVAL = 2.0

# Traffic announcements are checked far more often than source
# conflicts, because they can be: reading the RDS state is two file
# reads and a syscall, while checking MPRIS spawns playerctl. Polling
# both at the fast rate would multiply the subprocess cost for no gain
# -- Spotify starting a second late does not matter, a traffic
# bulletin starting four seconds late does.
TA_POLL_INTERVAL = 0.5

# Consecutive polls the TA flag must hold before interrupting. A weak
# signal can flip it for a single group, and switching source on that
# would stutter between Spotify and the radio.
TA_DEBOUNCE = 2

# Give up on an announcement that never ends. A stuck flag would
# otherwise hold the radio indefinitely.
TA_MAX_SECONDS = 300.0

# Separator for the playerctl format string. Chosen because it is
# vanishingly unlikely to appear in a track title, unlike a pipe or a
# dash.
FIELD_SEP = '\x1f'


# What was playing before the last pause, so `toggle` knows what to
# resume, plus the traffic-announcement bookkeeping. Runtime state, not
# settings: which source you were on is a property of this drive, not
# something to carry across an ignition cycle -- the radio should come
# back on the radio, not on whatever Spotify was doing last week.
STATE = 'source'


def _read_runtime() -> dict:
    return state.read(STATE)


def _write_runtime(data: dict) -> None:
    state.write(STATE, data)


def _write_last_active(name: str) -> None:
    state.update(STATE, active=name)


def _read_last_active() -> str:
    return str(_read_runtime().get('active', ''))


def _write_interrupted(name: str) -> None:
    """
    Remember what a traffic announcement took over from.

    Only the source name is persisted. The start time is kept in the
    supervisor's own state: this file has two writers -- the conflict
    resolver also updates `active` -- and a read-modify-write from the
    other one would keep refreshing the timestamp, so the timeout
    would never expire.
    """
    state.update(STATE, interrupted=name)


def _read_interrupted() -> str:
    return str(_read_runtime().get('interrupted', ''))


def request_ta_skip() -> bool:
    """
    Ask the supervisor to end the current announcement early.

    The supervisor runs in another process, so this leaves a token in
    the shared runtime file rather than acting directly. It is picked
    up within one poll -- half a second by default.

    Returns whether an announcement was actually in progress.
    """
    if not state.get(STATE, 'interrupted'):
        return False
    state.update(STATE, skip=True)
    return True


def _take_ta_skip() -> bool:
    """Consume the skip token, if one is waiting."""
    if not state.get(STATE, 'skip'):
        return False
    state.update(STATE, skip=None)
    return True


def traffic_enabled() -> bool:
    """
    Whether traffic announcements may interrupt.

    Read each poll rather than at startup, so toggling the setting
    takes effect without restarting the supervisor -- which matters
    when an announcement is being intrusive mid-drive.
    """
    return settings.get_bool('fm.traffic', True)


def _clear_interrupted() -> None:
    state.update(STATE, interrupted=None)


@dataclass
class Player:
    """An MPRIS player, or the FM radio standing in as one."""

    name: str
    status: str = ''
    artist: str = ''
    title: str = ''
    album: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def playing(self) -> bool:
        return self.status == PLAYING

    @property
    def label(self) -> str:
        parts = [p for p in (self.artist, self.title) if p]
        return ' - '.join(parts) if parts else self.name


@dataclass
class SourceState:
    active: str = ''                # name of the playing source, if any
    players: list[Player] = field(default_factory=list)
    fm_playing: bool = False
    paused: list[str] = field(default_factory=list)  # stopped to resolve
    traffic: bool = False           # a TA interrupt is in progress

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def conflict(self) -> bool:
        """More than one source producing audio at once."""
        return len([p for p in self.players if p.playing]) > 1


async def _run(*args: str, timeout: float = 5.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            f'{args[0]} not found',
            hint='pacman -S playerctl') from exc

    try:
        out, err = await asyncio.wait_for(proc.communicate(),
                                          timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError(f'timed out: {" ".join(args)}')

    if proc.returncode != 0:
        message = err.decode(errors='replace').strip()
        # "No players found" is a normal state, not a failure.
        if 'no players' in message.lower():
            return ''
        raise NotAvailableError(f'{args[0]} failed: {message}')

    return out.decode(errors='replace')


def parse_players(text: str) -> list[Player]:
    """
    Parse the output of `playerctl -a metadata --format ...`.

    One line per player, fields separated by FIELD_SEP. Players with no
    metadata still emit a line with empty fields, which is why the
    parse tolerates short rows rather than skipping them -- a paused
    player with no track is still a player worth knowing about.
    """
    players = []

    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(FIELD_SEP)
        while len(parts) < 5:
            parts.append('')

        name = parts[0].strip()
        if not name:
            continue

        players.append(Player(
            name=name,
            status=parts[1].strip(),
            artist=parts[2].strip(),
            title=parts[3].strip(),
            album=parts[4].strip(),
        ))

    return players


async def mpris_players() -> list[Player]:
    """Every MPRIS player currently registered."""
    fmt = FIELD_SEP.join((
        '{{playerName}}', '{{status}}',
        '{{artist}}', '{{title}}', '{{album}}',
    ))
    try:
        out = await _run(PLAYERCTL, '-a', 'metadata', '--format', fmt)
    except NotAvailableError:
        # Falling back to the bare list keeps this working when no
        # player exposes metadata, which is common for browsers.
        try:
            out = await _run(PLAYERCTL, '-l')
        except NotAvailableError:
            return []
        return [Player(name=n.strip())
                for n in out.splitlines() if n.strip()]

    return parse_players(out)


async def status() -> SourceState:
    """
    Every source and which one is actually making sound.

    FM is folded in as a player so callers do not have to special-case
    it -- from a UI's point of view it is just another source.
    """
    from carlib.radio import fm as radio

    players = await mpris_players()

    radio_state = await radio.status()
    if radio_state.playing:
        # A muted radio is running but not making sound, so it does not
        # count as the active source -- otherwise every switch away
        # from FM would look like a conflict.
        players.insert(0, Player(
            name=FM,
            status='Paused' if radio_state.paused else PLAYING,
            artist=radio_state.rds.ps or radio_state.name,
            title=radio_state.rds.radiotext
            or f'{radio_state.frequency:.1f} MHz',
        ))

    active = next((p.name for p in players if p.playing), '')

    return SourceState(
        active=active,
        players=players,
        fm_playing=radio_state.playing and not radio_state.paused,
    )


async def pause(name: str) -> None:
    """
    Pause one source by name.

    FM is paused rather than stopped -- see the module docstring.
    """
    if name == FM:
        from carlib.radio import fm as radio
        await radio.pause()
        return

    try:
        await _run(PLAYERCTL, '-p', name, 'pause')
    except NotAvailableError:
        pass        # gone, or does not support pausing


async def pause_others(keep: str = '') -> list[str]:
    """
    Pause every source except one. Returns what was paused.

    Pausing rather than stopping matters for Spotify: stopping spotifyd
    would tear down the Connect endpoint and the phone would lose the
    car as a target entirely.
    """
    state = await status()
    paused = []

    for player in state.players:
        if player.name == keep or not player.playing:
            continue
        await pause(player.name)
        paused.append(player.name)

    return paused


async def traffic_flag() -> bool:
    """
    Whether the tuned station is signalling a traffic announcement.

    Only meaningful while the FM pipeline is running: RDS is decoded
    from the tuned signal, so a stopped radio can never report one.
    Being paused is fine -- that is the point of pausing rather than
    stopping.
    """
    from carlib.radio import fm as radio

    try:
        state = await radio.status()
    except Exception:
        return False

    return bool(state.playing and state.rds.traffic_announcement)


async def select(name: str, **kwargs) -> SourceState:
    """
    Make one source the active one.

    For FM this starts playback, or unmutes a pipeline that is already
    running; for an MPRIS player it sends play. Everything else is
    then paused.
    """
    state = await status()
    known = {p.name for p in state.players} | {FM}

    if name not in known:
        raise NotFoundError('source', name, sorted(known))

    _write_last_active(name)

    # Start the wanted source first, then silence the rest. Pausing
    # first is not enough: pause_others only acts on what is currently
    # playing, so resuming a paused source would leave anything that
    # started in the meantime running alongside it.
    if name == FM:
        # play() resumes a paused pipeline and starts a stopped one,
        # so the distinction is not this module's to make.
        from carlib.radio import fm as radio
        await radio.play(**kwargs)
    else:
        try:
            await _run(PLAYERCTL, '-p', name, 'play')
        except NotAvailableError as exc:
            raise NotAvailableError(
                f'cannot start {name}: {exc}') from exc

    await pause_others(keep=name)

    return await status()


async def toggle_play() -> SourceState:
    """
    Pause what is playing, or resume what was paused last.

    Resuming goes through select(), which unmutes a running FM
    pipeline rather than restarting it and pauses everything else --
    so a toggle cannot leave two sources going.
    """
    state = await status()
    playing = [p for p in state.players if p.playing]

    if playing:
        current = playing[0].name
        _write_last_active(current)
        await pause(current)
        return await status()

    target = _read_last_active()

    # Nothing remembered -- this boot, or the remembered source has
    # gone away. Prefer a running FM pipeline, since unmuting it is
    # instant and needs no assumptions.
    known = {p.name for p in state.players}
    if target not in known:
        target = FM if FM in known else ''
    if not target:
        raise NotFoundError('source', 'any', sorted(known))

    return await select(target)


async def supervise(interval: float = POLL_INTERVAL,
                    priority: str = '',
                    traffic: bool | None = None,
                    ta_interval: float = TA_POLL_INTERVAL,
                    ta_timeout: float = TA_MAX_SECONDS
                    ) -> AsyncIterator[SourceState]:
    """
    Enforce one source at a time and handle traffic announcements,
    yielding whenever something changes.

    Two checks at two rates. Source conflicts are checked every
    `interval` because that costs a playerctl subprocess; the traffic
    flag every `ta_interval` because it costs two file reads. The loop
    runs at the faster rate and does the expensive check periodically.

    Polling rather than subscribing to MPRIS signals is deliberate:
    players come and go on the bus, and a subscription would have to be
    torn down and rebuilt each time. The same reasoning as the GPS
    supervisor -- a poll notices regardless and has no reconnection
    logic to get wrong.

    With `priority` set, that source wins a conflict. Otherwise the
    newcomer does, which is what a car radio does when you pick it
    from your phone. During an announcement FM holds priority
    regardless, so Spotify starting mid-bulletin cannot take it back.

    Traffic handling follows the `fm.traffic` setting unless `traffic`
    is given explicitly. `source.request_ta_skip()` ends the current
    announcement early.

        async for state in source.supervise():
            log(state.active)
    """
    # Seed from the current state rather than an empty set. On the
    # first poll everything looks like a newcomer otherwise, and a
    # conflict already in progress would be resolved arbitrarily
    # instead of in favour of whatever started most recently.
    try:
        previous_playing = {p.name for p in (await status()).players
                            if p.playing}
    except Exception:
        previous_playing = set()

    _clear_interrupted()        # stale state from a previous run
    ta_streak = 0
    interrupting = False
    interrupt_started = 0.0
    # Set when an interrupt is abandoned on timeout. Without it the
    # still-true flag would rebuild the streak and re-interrupt
    # immediately, oscillating between sources every few seconds.
    ta_exhausted = False
    last_conflict_check = 0.0

    while True:
        now = time.monotonic()
        event = None

        # --- traffic announcements, checked often -------------------
        # The setting is read every poll so it can be toggled without
        # restarting; an explicit `traffic` argument overrides it, for
        # a service unit that should never interrupt.
        ta_on = traffic if traffic is not None else traffic_enabled()

        if ta_on or interrupting:
            try:
                flag = await traffic_flag()
            except Exception:
                flag = False

            ta_streak = ta_streak + 1 if flag else 0

            if not flag:
                # The station has stopped signalling, so a future
                # announcement is allowed to interrupt again.
                ta_exhausted = False

            if interrupting:
                came_from = _read_interrupted()
                # Checked while the flag is still set, not only when it
                # clears -- a flag stuck true is exactly the case this
                # exists for.
                expired = (time.monotonic() - interrupt_started
                           > ta_timeout)
                skipped = _take_ta_skip()

                # Turning the setting off mid-announcement ends it too,
                # which is the obvious reading of switching it off.
                if not flag or expired or skipped or not ta_on:
                    interrupting = False
                    interrupt_started = 0.0
                    ta_streak = 0
                    if expired or skipped:
                        # The flag is probably still set. Without this
                        # the streak rebuilds and re-interrupts within
                        # a second, which for a skip would make the
                        # button appear to do nothing.
                        ta_exhausted = True
                    _clear_interrupted()
                    if came_from and came_from != FM:
                        try:
                            await select(came_from)
                        except (NotAvailableError, NotFoundError):
                            # The source went away mid-announcement --
                            # a phone disconnecting, say. Leave the
                            # radio playing rather than falling silent.
                            pass
                    event = await status()

            elif ta_on and ta_streak >= TA_DEBOUNCE and not ta_exhausted:
                _take_ta_skip()     # discard a token with nothing to skip
                state = await status()
                interrupt_started = time.monotonic()
                if state.active != FM:
                    _write_interrupted(state.active)
                    await select(FM)
                    interrupting = True
                    event = await status()
                    event.traffic = True
                else:
                    # Already listening to the station carrying it.
                    # Record nothing: there is nothing to restore.
                    interrupting = True

        # --- source conflicts, checked less often -------------------
        if now - last_conflict_check >= interval:
            last_conflict_check = now

            try:
                state = await status()
            except Exception:
                await asyncio.sleep(ta_interval)
                continue

            playing = {p.name for p in state.players if p.playing}
            intervened = []

            if len(playing) > 1:
                # Someone started while another was already going.
                # During an announcement the radio wins regardless.
                effective = FM if interrupting else priority

                if effective and effective in playing:
                    winner = effective
                else:
                    started = playing - previous_playing
                    if started:
                        winner = sorted(started)[0]
                    else:
                        # Both were already playing when we started
                        # watching, so there is no newcomer to favour.
                        # Keeping the first is arbitrary but stable.
                        winner = sorted(playing)[0]

                intervened = await pause_others(keep=winner)
                _write_last_active(winner)
                state = await status()
                state.paused = intervened
                playing = {p.name for p in state.players if p.playing}

            # Yield on intervention even when the playing set is
            # unchanged. With a priority set, blocking a hijack leaves
            # the same source playing -- but "I stopped Spotify taking
            # over" is exactly the event a caller wants to hear about.
            if playing != previous_playing or intervened:
                event = state
                previous_playing = playing

        if event is not None:
            event.traffic = interrupting
            yield event
            previous_playing = {p.name for p in event.players
                                if p.playing}

        await asyncio.sleep(ta_interval)
