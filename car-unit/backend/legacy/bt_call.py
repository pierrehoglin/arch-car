#!/usr/bin/env python3
"""
Call control over Bluetooth HFP via oFono.

Setup (once):
    sudo pacman -S ofono
    sudo systemctl enable --now ofono

    # Stop WirePlumber claiming HFP for itself:
    mkdir -p ~/.config/wireplumber/wireplumber.conf.d
    cat > ~/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf <<'EOF'
    monitor.bluez.properties = {
      bluez5.hfphsp-backend = "ofono"
    }
    EOF

Order matters on boot: bluetooth -> ofono -> wireplumber. If Interfaces
comes back empty from `modems`, restart in that order.

Run:
    ./bt_call.py modems                          # discover modems
    ./bt_call.py online   20:F0:94:03:AB:DF      # power up + bring online
    ./bt_call.py dial     20:F0:94:03:AB:DF +46701234567
    ./bt_call.py calls    "Pierre Pixel"         # name works too
    ./bt_call.py answer   20:F0:94:03:AB:DF
    ./bt_call.py hangup   20:F0:94:03:AB:DF
    ./bt_call.py monitor  20:F0:94:03:AB:DF      # watch call state live
    ./bt_call.py network  20:F0:94:03:AB:DF      # operator, signal strength
    ./bt_call.py volume   20:F0:94:03:AB:DF --speaker 80 --mic 60
    ./bt_call.py volume   20:F0:94:03:AB:DF --mute on
    ./bt_call.py tones    20:F0:94:03:AB:DF '1234#'   # DTMF in a call
    ./bt_call.py voice    20:F0:94:03:AB:DF on   # phone's voice assistant
    ./bt_call.py handsfree 20:F0:94:03:AB:DF     # HFP features, battery

The modem may be given as a MAC (either notation), an object path
fragment, or a substring of the modem name. Run `modems` first to see
what is connected.

oFono's D-Bus policy is root-only by default. To run unprivileged, add
/etc/dbus-1/system.d/ofono-user.conf granting your user send access to
org.ofono, then `sudo systemctl reload dbus`.
"""

import sys
import asyncio
import argparse

from sdbus import (
    sd_bus_open_system,
    set_default_bus,
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_signal_async,
)

BUS_NAME = 'org.ofono'


class OfonoManager(DbusInterfaceCommonAsync,
                   interface_name='org.ofono.Manager'):

    @dbus_method_async(result_signature='a(oa{sv})')
    async def get_modems(self) -> list[tuple[str, dict]]:
        raise NotImplementedError


class OfonoModem(DbusInterfaceCommonAsync,
                 interface_name='org.ofono.Modem'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async(input_signature='sv')
    async def set_property(self, name: str,
                           value: tuple[str, object]) -> None:
        raise NotImplementedError


class VoiceCallManager(DbusInterfaceCommonAsync,
                       interface_name='org.ofono.VoiceCallManager'):

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def dial(self, number: str, hide_callerid: str) -> str:
        raise NotImplementedError

    @dbus_method_async(result_signature='a(oa{sv})')
    async def get_calls(self) -> list[tuple[str, dict]]:
        raise NotImplementedError

    @dbus_method_async()
    async def hangup_all(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def answer(self) -> None:
        raise NotImplementedError

    @dbus_signal_async('oa{sv}')
    def call_added(self) -> tuple[str, dict]:
        raise NotImplementedError

    @dbus_signal_async('o')
    def call_removed(self) -> str:
        raise NotImplementedError


class VoiceCall(DbusInterfaceCommonAsync,
                interface_name='org.ofono.VoiceCall'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async()
    async def hangup(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def answer(self) -> None:
        raise NotImplementedError

    @dbus_signal_async('sv')
    def property_changed(self) -> tuple[str, tuple[str, object]]:
        raise NotImplementedError


class CallVolume(DbusInterfaceCommonAsync,
                 interface_name='org.ofono.CallVolume'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async(input_signature='sv')
    async def set_property(self, name: str,
                           value: tuple[str, object]) -> None:
        raise NotImplementedError


class Handsfree(DbusInterfaceCommonAsync,
                interface_name='org.ofono.Handsfree'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async(input_signature='sv')
    async def set_property(self, name: str,
                           value: tuple[str, object]) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='s')
    async def send_tones(self, tones: str) -> None:
        raise NotImplementedError


class NetworkRegistration(DbusInterfaceCommonAsync,
                          interface_name='org.ofono.NetworkRegistration'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError


def unwrap(variant):
    """oFono properties arrive as (signature, value) tuples."""
    if isinstance(variant, tuple) and len(variant) == 2:
        return variant[1]
    return variant


def props(raw: dict) -> dict:
    return {k: unwrap(v) for k, v in raw.items()}


async def resolve_modem(bus, match: str) -> tuple[str, dict]:
    """
    Find the modem matching `match`, which may be a MAC in either
    notation (20:F0:94:.. or 20_F0_94_..), an object path fragment, or a
    case-insensitive substring of the modem Name.
    """
    manager = OfonoManager.new_proxy(BUS_NAME, '/', bus)
    modems = await manager.get_modems()

    if not modems:
        raise RuntimeError('no modems; is the phone connected over HFP?')

    key = match.upper().replace(':', '_')
    hits = []
    for path, raw in modems:
        p = props(raw)
        name = (p.get('Name') or '').upper()
        serial = (p.get('Serial') or '').upper().replace(':', '_')
        if key in path.upper() or key in serial or match.upper() in name:
            hits.append((path, p))

    if not hits:
        known = ', '.join(props(r).get('Name', p) for p, r in modems)
        raise RuntimeError(f'no modem matching {match!r}; have: {known}')
    if len(hits) > 1:
        names = ', '.join(p.get('Name', path) for path, p in hits)
        raise RuntimeError(f'{match!r} is ambiguous: {names}')

    return hits[0]


# --- Commands --------------------------------------------------------------

async def cmd_modems() -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    manager = OfonoManager.new_proxy(BUS_NAME, '/', bus)
    modems = await manager.get_modems()

    if not modems:
        print('No modems. Connect the phone and check HFP is registered.')
        return

    for path, raw in modems:
        p = props(raw)
        print(f"{p.get('Name', '?')}  [{p.get('Type', '?')}]")
        print(f"  path:       {path}")
        print(f"  serial:     {p.get('Serial', '-')}")
        print(f"  powered:    {p.get('Powered')}")
        print(f"  online:     {p.get('Online')}")
        ifaces = p.get('Interfaces') or []
        print(f"  interfaces: {', '.join(ifaces) if ifaces else '(none)'}")
        if not ifaces:
            print('  -> empty interfaces usually means the HFP link is '
                  'down; restart bluetooth, then ofono, then wireplumber.')


async def cmd_online(modem_sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, p = await resolve_modem(bus, modem_sel)
    modem = OfonoModem.new_proxy(BUS_NAME, path, bus)

    if not p.get('Powered'):
        await modem.set_property('Powered', ('b', True))
        print('powered on')
    if not p.get('Online'):
        await modem.set_property('Online', ('b', True))
        print('online')

    # Re-read so the user sees the interfaces that appeared.
    p = props(await modem.get_properties())
    print(f"interfaces: {', '.join(p.get('Interfaces') or []) or '(none)'}")


async def cmd_dial(modem_sel: str, number: str, hide_id: bool) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    vcm = VoiceCallManager.new_proxy(BUS_NAME, path, bus)

    call_path = await vcm.dial(number, 'enabled' if hide_id else 'default')
    print(f'calling {number}')
    print(f'call object: {call_path}')

    call = VoiceCall.new_proxy(BUS_NAME, call_path, bus)
    # Show state transitions until the call ends or the user interrupts.
    try:
        while True:
            try:
                p = props(await call.get_properties())
            except Exception:
                print('call ended')
                break
            state = p.get('State', '?')
            print(f'  state: {state}')
            if state == 'disconnected':
                break
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print('\nhanging up')
        try:
            await call.hangup()
        except Exception:
            pass


async def cmd_calls(modem_sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    vcm = VoiceCallManager.new_proxy(BUS_NAME, path, bus)
    calls = await vcm.get_calls()

    if not calls:
        print('No active calls.')
        return

    for call_path, raw in calls:
        p = props(raw)
        who = p.get('Name') or p.get('LineIdentification') or 'unknown'
        print(f"{p.get('State', '?'):<14} {who:<24} "
              f"{p.get('LineIdentification', '')}")
        print(f"  {call_path}")


async def cmd_answer(modem_sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    vcm = VoiceCallManager.new_proxy(BUS_NAME, path, bus)
    await vcm.answer()
    print('answered')


async def cmd_hangup(modem_sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    vcm = VoiceCallManager.new_proxy(BUS_NAME, path, bus)
    await vcm.hangup_all()
    print('hung up')


async def cmd_network(modem_sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    net = NetworkRegistration.new_proxy(BUS_NAME, path, bus)
    p = props(await net.get_properties())

    print(f"operator: {p.get('Name', '-')}")
    print(f"status:   {p.get('Status', '-')}")
    print(f"strength: {p.get('Strength', '-')}%")
    print(f"tech:     {p.get('Technology', '-')}")


async def cmd_volume(modem_sel: str, speaker: int | None,
                     mic: int | None, mute: str | None) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    cv = CallVolume.new_proxy(BUS_NAME, path, bus)

    if speaker is not None:
        await cv.set_property('SpeakerVolume', ('y', max(0, min(100, speaker))))
    if mic is not None:
        await cv.set_property('MicrophoneVolume', ('y', max(0, min(100, mic))))
    if mute is not None:
        await cv.set_property('Muted', ('b', mute == 'on'))

    p = props(await cv.get_properties())
    print(f"speaker:    {p.get('SpeakerVolume', '-')}%")
    print(f"microphone: {p.get('MicrophoneVolume', '-')}%")
    print(f"muted:      {p.get('Muted', '-')}")


async def cmd_tones(modem_sel: str, tones: str) -> None:
    """Send DTMF digits during an active call, e.g. for phone menus."""
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    hf = Handsfree.new_proxy(BUS_NAME, path, bus)
    await hf.send_tones(tones)
    print(f'sent: {tones}')


async def cmd_voice(modem_sel: str, state: str) -> None:
    """Trigger the phone's own voice assistant over HFP."""
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    hf = Handsfree.new_proxy(BUS_NAME, path, bus)

    if state in ('on', 'off'):
        await hf.set_property('VoiceRecognition', ('b', state == 'on'))

    p = props(await hf.get_properties())
    print(f"voice recognition: {p.get('VoiceRecognition', '-')}")


async def cmd_handsfree(modem_sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    hf = Handsfree.new_proxy(BUS_NAME, path, bus)
    p = props(await hf.get_properties())

    features = p.get('Features') or []
    print(f"features:          {', '.join(features) or '-'}")
    print(f"voice recognition: {p.get('VoiceRecognition', '-')}")
    print(f"battery:           {p.get('BatteryChargeLevel', '-')}")
    print(f"in-band ringing:   {p.get('InbandRinging', '-')}")


async def cmd_monitor(modem_sel: str) -> None:
    """Watch for calls appearing and disappearing. Ctrl-C to stop."""
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, _ = await resolve_modem(bus, modem_sel)
    vcm = VoiceCallManager.new_proxy(BUS_NAME, path, bus)

    print('watching for calls (ctrl-c to stop)')

    async def watch_added():
        async for call_path, raw in vcm.call_added:
            p = props(raw)
            who = p.get('Name') or p.get('LineIdentification') or 'unknown'
            direction = ('incoming' if p.get('State') == 'incoming'
                         else 'outgoing')
            print(f'[{direction}] {who}  {p.get("State", "")}')
            print(f'  {call_path}')

    async def watch_removed():
        async for call_path in vcm.call_removed:
            print(f'[ended]    {call_path}')

    await asyncio.gather(watch_added(), watch_removed())


# --- Entry point -----------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description='Call control over Bluetooth HFP via oFono.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    # `modems` is how you discover what to pass, so it takes no selector.
    sub.add_parser('modems', help='list modems and their state')

    def with_modem(name: str, help_text: str):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('modem', metavar='MAC|NAME',
                       help='MAC, path fragment or modem name')
        return p

    with_modem('online', 'power up and bring the modem online')
    with_modem('calls', 'list active calls')
    with_modem('answer', 'answer the incoming call')
    with_modem('hangup', 'hang up all calls')
    with_modem('network', 'operator and signal strength')
    with_modem('monitor', 'watch call state changes')
    with_modem('handsfree', 'HFP features, phone battery, ring mode')

    dial = with_modem('dial', 'place a call')
    dial.add_argument('number')
    dial.add_argument('--hide-id', action='store_true',
                      help='withhold caller ID')

    vol = with_modem('volume', 'get or set call audio levels')
    vol.add_argument('--speaker', type=int, metavar='0-100')
    vol.add_argument('--mic', type=int, metavar='0-100')
    vol.add_argument('--mute', choices=['on', 'off'])

    tones = with_modem('tones', 'send DTMF digits during a call')
    tones.add_argument('digits', help='e.g. 1234#')

    voice = with_modem('voice', "toggle the phone's voice assistant")
    voice.add_argument('state', nargs='?', choices=['on', 'off'],
                       help='omit to just read the current state')

    args = ap.parse_args()

    handlers = {
        'online':    cmd_online,
        'calls':     cmd_calls,
        'answer':    cmd_answer,
        'hangup':    cmd_hangup,
        'network':   cmd_network,
        'monitor':   cmd_monitor,
        'handsfree': cmd_handsfree,
    }

    try:
        if args.cmd == 'modems':
            asyncio.run(cmd_modems())
        elif args.cmd == 'dial':
            asyncio.run(cmd_dial(args.modem, args.number, args.hide_id))
        elif args.cmd == 'volume':
            asyncio.run(cmd_volume(args.modem, args.speaker,
                                   args.mic, args.mute))
        elif args.cmd == 'tones':
            asyncio.run(cmd_tones(args.modem, args.digits))
        elif args.cmd == 'voice':
            asyncio.run(cmd_voice(args.modem, args.state))
        else:
            asyncio.run(handlers[args.cmd](args.modem))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
