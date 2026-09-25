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
import contextlib
from dataclasses import dataclass, field, asdict
from typing import AsyncIterator

from carlib.core import settings, state
from carlib.core.errors import (CarError, NotAvailableError,
                                NotFoundError)

PLAYERCTL = 'playerctl'

# The pseudo-source for our own radio pipeline, which has no MPRIS
# interface to find.
FM = 'fm'
# A phone over AVRCP, folded in beside FM. It is not an MPRIS
# player and never appears on the bus, so without this the
# supervisor cannot see it -- starting music on the phone would
# leave the radio playing underneath, and the two would mix.
BT = 'bluetooth'

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
    # Milliseconds. MPRIS reports microseconds; converted on the way
    # in so every caller works in the same unit as AVRCP, which
    # already uses milliseconds.
    duration: int | None = None
    position: int | None = None
    # A URL, usually on the provider's CDN. Empty for anything that
    # does not publish one -- AVRCP never does.
    art: str = ''
    # Changes per track, so a screen can tell a new song from the same
    # one playing on.
    track_id: str = ''

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


def _micros(raw: str) -> int | None:
    """
    Microseconds from playerctl as milliseconds.

    Absent for a player with no track, and playerctl prints the
    placeholder rather than an empty field when a variable does not
    resolve -- so anything that is not a number is nothing.
    """
    text = raw.strip()
    if not text or not text.isdigit():
        return None
    return int(text) // 1000


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
        while len(parts) < 9:
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
            duration=_micros(parts[5]),
            position=_micros(parts[6]),
            art=parts[7].strip(),
            track_id=parts[8].strip(),
        ))

    return players


async def mpris_players() -> list[Player]:
    """Every MPRIS player currently registered."""
    fmt = FIELD_SEP.join((
        '{{playerName}}', '{{status}}',
        '{{artist}}', '{{title}}', '{{album}}',
        '{{mpris:length}}', '{{position}}',
        '{{mpris:artUrl}}', '{{mpris:trackid}}',
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

    # The phone, if it has a media session. Folded in like FM so
    # the supervisor arbitrates all three without special-casing
    # any of them.
    with contextlib.suppress(CarError):
        phone = await _from_avrcp()
        if phone.present and phone.title:
            players.insert(0, Player(
                name=BT,
                status=(PLAYING if phone.status == 'playing'
                        else 'Paused'),
                artist=phone.artist,
                title=phone.title,
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

    if name == BT:
        # AVRCP, not playerctl: the phone is not on the bus.
        from carlib.bluetooth import media
        with contextlib.suppress(CarError):
            await media.control('pause')
        return

    try:
        await _run(PLAYERCTL, '-p', name, 'pause')
    except NotAvailableError:
        pass        # gone, or does not support pausing


def _same_track(a: Player, b: Player) -> bool:
    """
    Whether two sources are playing the same thing.

    Title only, normalised. Artist and album are not comparable
    across transports -- playerctl joins several artists into one
    string where AVRCP sends a single name, and albums are
    abbreviated differently -- so requiring those to match means
    never matching.
    """
    if not a.title or not b.title:
        return False

    return (' '.join(a.title.split()).casefold()
            == ' '.join(b.title.split()).casefold())

async def pause_others(keep: str = '') -> list[str]:
    """
    Pause every source except one. Returns what was paused.

    Pausing rather than stopping matters for Spotify: stopping spotifyd
    would tear down the Connect endpoint and the phone would lose the
    car as a target entirely.
    """
    state = await status()
    winner = next((p for p in state.players if p.name == keep), None)
    paused = []

    for player in state.players:
        if player.name == keep or not player.playing:
            continue

        # One session arriving twice is not a conflict. A phone
        # playing Spotify over Bluetooth is reported by AVRCP and
        # by the Connect device both; pausing the 'other' one
        # pauses the session, stopping the music that just
        # started.
        if winner is not None and _same_track(winner, player):
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

    Uses Rds.announcement, which requires TP as well as TA. TA on its
    own also means "I carry EON data about bulletins elsewhere", which
    some stations signal permanently.
    """
    from carlib.radio import fm as radio

    try:
        state = await radio.status()
    except Exception:
        return False

    return bool(state.playing and state.rds.announcement)


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


# --- One shape for every player ---------------------------------------------
#
# AVRCP and MPRIS carry the same things under different names, so the
# screens differ only in which one they read. AVRCP has no artwork --
# the profile can carry it, but BlueZ does not expose it -- and
# neither has a queue.

BLUETOOTH = 'bluetooth'
SPOTIFY = 'spotify'

# AVRCP's set, which is the smaller of the two. MPRIS gets the same
# words through playerctl, with `prev` spelled out on the way.
ACTIONS = ('play', 'pause', 'stop', 'next', 'prev', 'forward', 'rewind')

# What a source might be called on MPRIS, in the order to try.
#
# spotifyd is what runs on the unit; the desktop client is plain
# `spotify`, which is what a development machine has. Both answer to
# the same screen, so the source name covers either.
#
# Order matters because one name is a prefix of the other: looking for
# `spotify` first would match spotifyd as well, and on the unit the
# daemon would be found under the wrong name.
CANDIDATES: dict[str, tuple[str, ...]] = {
    SPOTIFY: ('spotifyd', 'spotify'),
}


@dataclass
class NowPlaying:
    """What a source is playing, however it was asked."""

    source: str
    # Who it is coming from: the phone's name over Bluetooth, the
    # player's name over MPRIS.
    device: str = ''
    status: str = ''
    title: str = ''
    artist: str = ''
    album: str = ''
    # Milliseconds, both.
    duration: int | None = None
    position: int | None = None
    art: str = ''
    track_id: str = ''
    # Whether the position can be set.
    #
    # MPRIS can. AVRCP cannot: BlueZ exposes Position read-only and
    # offers no seek method, and the relative FastForward and Rewind
    # are press-and-hold operations most phone apps ignore. So a
    # slider over Bluetooth is a readout, not a control.
    seekable: bool = False
    # Whether anything is there at all. A phone with no media session
    # has no player, which is not an error -- it is the ordinary state
    # before you press play.
    present: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# How long to wait for a player to catch up after a command.
#
# Both transports answer the command immediately and change state
# afterwards: playerctl returns as soon as the method is dispatched,
# and AVRCP has to reach the phone and come back. Reading straight
# away returns what was playing before the button was pressed.
SETTLE_TIMEOUT = 1.2
SETTLE_INTERVAL = 0.08

# One command produces more than one notification, and they do not
# arrive together. Pausing sends the status first and the final
# position after it, so a reading taken the moment the status changes
# carries the position from before the command.
#
# This is how long to keep reading after the status has settled,
# waiting for the position to follow. Short, because it is the gap
# between two notifications about the same event, not a round trip.
POSITION_GRACE = 0.6

# How close counts as having arrived after a seek. The track keeps
# playing while we ask, so the position read back is always a little
# past the one that was set.
SEEK_ARRIVED = 1000


def _plain(text: str) -> str:
    """Case and spacing removed, for comparing two spellings."""
    return ' '.join(text.split()).casefold()


def same_track(a: 'NowPlaying', b: 'NowPlaying') -> bool:
    """
    Whether two sources are playing the same thing.

    Which happens for real, and often: a phone playing Spotify over
    Bluetooth is one Connect session surfacing twice. AVRCP reports
    it because the phone's media session is Spotify, and the Connect
    device reports it because it is the same session.

    The title alone decides it. Artist and album are not comparable
    across the two: playerctl joins several artists into one string
    while AVRCP sends a single name, and albums are abbreviated
    differently -- so requiring those to match means never matching.

    Two sources playing the same title at the same moment is the same
    audio. The alternative -- two devices independently starting the
    same song within seconds of each other -- is not something worth
    designing for.
    """
    if not a.title or not b.title:
        return False

    return _plain(a.title) == _plain(b.title)


def signature(playing: 'NowPlaying') -> tuple:
    """
    What counts as a change worth noticing.

    Position is left out deliberately. It moves every second by
    definition, so a comparison including it would report a change
    the moment anything was read twice.
    """
    return (playing.present, playing.status, playing.title,
            playing.artist, playing.album, playing.track_id)


def _normalise(status: str) -> str:
    """
    AVRCP says 'playing', MPRIS says 'Playing'.

    One vocabulary out, so a screen does not have to know which
    transport it is looking at.
    """
    lowered = status.strip().lower()
    return lowered if lowered in ('playing', 'paused', 'stopped') else ''


async def now_playing(source: str) -> NowPlaying:
    """
    What is playing on one source.

    Never raises for an absent player: a phone that has not started
    anything, or spotifyd with nothing queued, reports `present` false
    rather than an error. Only a transport that cannot be reached at
    all is worth reporting as a failure.
    """
    if source == BLUETOOTH:
        return await _from_avrcp()
    return await _from_mpris(source)


async def _from_avrcp() -> NowPlaying:
    from carlib.bluetooth import media

    try:
        player = await media.status()
    except CarError:
        return NowPlaying(source=BLUETOOTH)

    return NowPlaying(
        source=BLUETOOTH,
        device=player.device_name,
        status=_normalise(player.status),
        title=player.track.title,
        artist=player.track.artist,
        album=player.track.album,
        duration=player.track.duration,
        position=player.position,
        present=True,
    )


async def find_mpris(source: str) -> Player | None:
    """
    The MPRIS player behind a source name, if it is running.

    Matched on a prefix: spotifyd registers as
    org.mpris.MediaPlayer2.spotifyd.instance603, and playerctl reports
    the instance suffix for some builds -- an exact match would break
    on a restart.
    """
    players = await mpris_players()

    for wanted in CANDIDATES.get(source, (source,)):
        for player in players:
            if player.name.startswith(wanted):
                return player

    return None


async def _from_mpris(source: str) -> NowPlaying:
    player = await find_mpris(source)
    if player is None:
        return NowPlaying(source=source)

    return NowPlaying(
        source=source,
        device=player.name,
        status=_normalise(player.status),
        title=player.title,
        artist=player.artist,
        album=player.album,
        duration=player.duration,
        position=player.position,
        art=player.art,
        track_id=player.track_id,
        seekable=True,
        present=True,
    )


async def command(source: str, action: str) -> NowPlaying:
    """
    Drive a source, whichever transport it is on.

    The action names are AVRCP's, since they are the smaller set;
    MPRIS gets the same words through playerctl.
    """
    before = await now_playing(source)

    if source == BLUETOOTH:
        from carlib.bluetooth import media
        await media.control(action)
    else:
        # Resolved rather than assumed: the name has to be the one
        # that is actually registered, which on a development machine
        # is the desktop client and on the unit is the daemon.
        player = await find_mpris(source)
        if player is None:
            raise NotFoundError('player', source,
                                [p.name for p in await mpris_players()])

        verb = {'prev': 'previous'}.get(action, action)
        await _run(PLAYERCTL, '-p', player.name, verb)

    return await _settled(source, before)


async def seek(source: str, ms: int) -> NowPlaying:
    """
    Move to a position in the track.

    MPRIS only. Nothing about AVRCP allows it, so asking says so
    rather than doing nothing and reporting success.
    """
    if source == BLUETOOTH:
        raise NotAvailableError(
            'Bluetooth playback cannot be seeked',
            hint='AVRCP has no absolute position, and BlueZ exposes '
                 'the property read-only')

    player = await find_mpris(source)
    if player is None:
        raise NotFoundError('player', source,
                            [p.name for p in await mpris_players()])

    target = max(0, int(ms))
    await _run(PLAYERCTL, '-p', player.name,
               'position', f'{target / 1000:.3f}')

    return await _reached(source, target)


async def _reached(source: str, target: int) -> NowPlaying:
    """
    Read until the player reports being roughly where it was sent.

    Roughly, because it carries on playing while we ask: by the time
    the position comes back it has moved on from the number we set.
    Anything within a second is the seek having landed.
    """
    deadline = time.monotonic() + SETTLE_TIMEOUT
    playing = await now_playing(source)

    while time.monotonic() < deadline:
        if (playing.position is not None
                and abs(playing.position - target) < SEEK_ARRIVED):
            return playing

        await asyncio.sleep(SETTLE_INTERVAL)
        playing = await now_playing(source)

    return playing


async def _settled(source: str, before: NowPlaying) -> NowPlaying:
    """
    Read until the player has finished responding, or time runs out.

    Two waits, because one command produces two notifications.

    First for the state: without it the answer describes the player
    before the command, and a screen that applies it puts the old
    track back over the right one -- which then arrives again on the
    stream a moment later, so the display flickers.

    Then for the position, which follows separately. AVRCP sends the
    playback status and the position as different events, and BlueZ
    reports whichever it has; read too early and the position is the
    one from before the command, so a pause appears to move the track
    backwards.

    Giving up is correct in both cases. A command that changes
    nothing -- pause when already paused, next at the end of a queue
    the phone will not advance past -- has no second notification to
    wait for, and the reading in hand is the answer.
    """
    was = signature(before)

    deadline = time.monotonic() + SETTLE_TIMEOUT
    playing = await now_playing(source)

    while signature(playing) == was and time.monotonic() < deadline:
        await asyncio.sleep(SETTLE_INTERVAL)
        playing = await now_playing(source)

    if signature(playing) == was:
        # Nothing changed, so there is no position to wait for.
        return playing

    return await _positioned(source, playing, before.position)


async def _positioned(source: str, playing: NowPlaying,
                      was: int | None) -> NowPlaying:
    """
    Wait for the position to be reported for the new state.

    Only where it can be stale. A track change resets the position to
    zero and BlueZ knows that immediately; it is stopping and starting
    within one track where the cached value lags.
    """
    if playing.position is None or playing.position != was:
        return playing

    deadline = time.monotonic() + POSITION_GRACE

    while time.monotonic() < deadline:
        await asyncio.sleep(SETTLE_INTERVAL)
        fresh = await now_playing(source)

        if fresh.position != was:
            return fresh

    return playing
