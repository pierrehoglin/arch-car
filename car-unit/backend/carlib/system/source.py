"""
Audio source coordination.

A car head unit has one source at a time: radio, or Spotify, or the
phone over Bluetooth. PipeWire will happily mix them all, which is not
what anyone wants, so something has to arbitrate.

MPRIS is the common handle. spotifyd, browsers and Bluetooth A2DP all
expose it, and `playerctl` drives it. FM is the exception -- it is a
raw rtl_fm pipeline with no MPRIS interface -- so it is handled
directly through carlib.radio.fm.

FM is muted rather than stopped when another source takes over. RDS is
only decodable while tuned, so stopping the pipeline would mean no
traffic announcements; a muted one keeps decoding. The cost is about
8% of one Pi 4 core, measured, which is worth paying to avoid a
1.5 second gap at the start of every announcement.

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

import asyncio
from dataclasses import dataclass, field, asdict
from typing import AsyncIterator

from carlib.core.errors import NotAvailableError, NotFoundError

PLAYERCTL = 'playerctl'

# The pseudo-source for our own radio pipeline, which has no MPRIS
# interface to find.
FM = 'fm'

# playerctl reports these; only the first means audio is coming out.
PLAYING = 'Playing'

POLL_INTERVAL = 2.0

# Separator for the playerctl format string. Chosen because it is
# vanishingly unlikely to appear in a track title, unlike a pipe or a
# dash.
FIELD_SEP = '\x1f'


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
            status='Paused' if radio_state.muted else PLAYING,
            artist=radio_state.rds.ps or radio_state.name,
            title=radio_state.rds.radiotext
            or f'{radio_state.frequency:.1f} MHz',
        ))

    active = next((p.name for p in players if p.playing), '')

    return SourceState(
        active=active,
        players=players,
        fm_playing=radio_state.playing and not radio_state.muted,
    )


async def pause(name: str) -> None:
    """
    Pause one source by name.

    FM is muted rather than stopped -- see the module docstring.
    """
    if name == FM:
        from carlib.radio import fm as radio
        await radio.mute()
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


async def select(name: str, **kwargs) -> SourceState:
    """
    Make one source the active one.

    For FM this starts playback; for an MPRIS player it sends play.
    Either way everything else is paused first, so the switch is not
    briefly two sources at once.
    """
    state = await status()
    known = {p.name for p in state.players} | {FM}

    if name not in known:
        raise NotFoundError('source', name, sorted(known))

    await pause_others(keep=name)

    if name == FM:
        from carlib.radio import fm as radio
        state = await radio.status()
        if state.playing:
            await radio.unmute()
        else:
            await radio.play(**kwargs)
    else:
        try:
            await _run(PLAYERCTL, '-p', name, 'play')
        except NotAvailableError as exc:
            raise NotAvailableError(
                f'cannot start {name}: {exc}') from exc

    return await status()


async def toggle_play() -> SourceState:
    """Play/pause whatever source is current, without switching."""
    state = await status()

    if state.fm_playing:
        from carlib.radio import fm as radio
        await radio.mute()
        return await status()

    target = state.active or next(
        (p.name for p in state.players), '')
    if not target:
        raise NotFoundError('source', 'any', [])

    if target == FM:
        from carlib.radio import fm as radio
        await radio.play()
    else:
        await _run(PLAYERCTL, '-p', target, 'play-pause')

    return await status()


async def supervise(interval: float = POLL_INTERVAL,
                    priority: str = '') -> AsyncIterator[SourceState]:
    """
    Enforce one source at a time, yielding when something changes.

    Polling rather than subscribing to MPRIS signals is deliberate:
    players come and go on the bus, and a subscription would have to be
    torn down and rebuilt each time. The same reasoning as the GPS
    supervisor -- a poll notices regardless and has no reconnection
    logic to get wrong.

    With `priority` set, that source wins a conflict. Otherwise the
    newcomer does, which is what a car radio does when you pick it from
    your phone.

        async for state in source.supervise(priority='fm'):
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

    while True:
        try:
            state = await status()
        except Exception:
            await asyncio.sleep(interval)
            continue

        playing = {p.name for p in state.players if p.playing}

        intervened = []

        if len(playing) > 1:
            # Someone started while another was already going.
            if priority and priority in playing:
                winner = priority
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
            state = await status()
            state.paused = intervened
            playing = {p.name for p in state.players if p.playing}

        # Yield on intervention even when the playing set is unchanged.
        # With a priority set, blocking a hijack leaves the same source
        # playing -- but "I stopped Spotify taking over" is exactly the
        # event a caller wants to hear about.
        if playing != previous_playing or intervened:
            yield state
            previous_playing = playing

        await asyncio.sleep(interval)
