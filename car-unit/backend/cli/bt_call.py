#!/usr/bin/env python3
"""
Call control over Bluetooth HFP.

    ./bt-call modems                        # discover, then use a name/MAC
    ./bt-call online
    ./bt-call dial +46701234567
    ./bt-call answer
    ./bt-call hangup
    ./bt-call list
    ./bt-call monitor                       # live call events
    ./bt-call network
    ./bt-call handsfree
    ./bt-call volume --speaker 80 --mic 60
    ./bt-call tones '1234#'
    ./bt-call voice on

The modem selector is optional when one phone is connected. Add it as
the last argument otherwise:

    ./bt-call dial +46701234567 "Pierre Pixel"

Needs sudo unless /etc/dbus-1/system.d/ofono-user.conf grants access.
"""

import sys
import asyncio
import argparse

from carlib.bluetooth import calls
from carlib.core.output import (
    run, emit_json, add_target, dash, global_flags, parse_args)


async def cmd_modems(args) -> None:
    found = await calls.modems()
    if args.json:
        emit_json(found)
        return

    if not found:
        print('No modems. Is the phone connected over HFP?')
        return

    for m in found:
        flag = 'ready' if m.ready else 'not ready'
        print(f'{m.name}  [{m.type}]  {flag}')
        print(f'  serial:     {m.serial or "-"}')
        print(f'  powered:    {m.powered}')
        print(f'  online:     {m.online}')
        print(f'  interfaces: {", ".join(m.interfaces) or "(none)"}')
        if not m.ready:
            print('  -> run `online`; if that fails restart in order: '
                  'bluetooth, ofono, wireplumber')


async def cmd_online(args) -> None:
    m = await calls.online(args.target)
    if args.json:
        emit_json(m)
        return
    print(f'{m.name}: powered={m.powered} online={m.online}')
    print(f'interfaces: {", ".join(m.interfaces) or "(none)"}')


async def cmd_dial(args) -> None:
    call = await calls.dial(args.number, args.target, args.hide_id)
    if args.json:
        emit_json(call)
        return

    print(f'calling {args.number}')
    # Follow the call until it ends; ctrl-c hangs up.
    try:
        while True:
            current = await calls.call_state(call.path)
            if current is None:
                print('  call ended')
                break
            print(f'  {current.state}')
            if current.state == 'disconnected':
                break
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print('\nhanging up')
        await calls.hangup(call_path=call.path)


async def cmd_list(args) -> None:
    active = await calls.active(args.target)
    if args.json:
        emit_json(active)
        return
    if not active:
        print('No active calls.')
        return
    for c in active:
        print(f'{c.state:<14} {c.who:<24} {c.number}')
        print(f'  {c.path}')


async def cmd_answer(args) -> None:
    await calls.answer(args.target)
    print('answered')


async def cmd_hangup(args) -> None:
    await calls.hangup(args.target)
    print('hung up')


async def cmd_network(args) -> None:
    info = await calls.network(args.target)
    if args.json:
        emit_json(info)
        return
    print(f'operator: {info.operator or "-"}')
    print(f'status:   {info.status or "-"}')
    print(f'strength: {dash(info.strength, "%")}')
    print(f'tech:     {info.technology or "-"}')


async def cmd_handsfree(args) -> None:
    info = await calls.handsfree(args.target)
    if args.json:
        emit_json(info)
        return
    print(f'features:          {", ".join(info.features) or "-"}')
    print(f'voice recognition: {info.voice_recognition}')
    print(f'phone battery:     {dash(info.battery)}')
    print(f'in-band ringing:   {info.inband_ringing}')


async def cmd_volume(args) -> None:
    muted = None if args.mute is None else (args.mute == 'on')
    info = await calls.volume(args.target, args.speaker, args.mic, muted)
    if args.json:
        emit_json(info)
        return
    print(f'speaker:    {dash(info.speaker, "%")}')
    print(f'microphone: {dash(info.microphone, "%")}')
    print(f'muted:      {info.muted}')


async def cmd_tones(args) -> None:
    await calls.send_tones(args.digits, args.target)
    print(f'sent: {args.digits}')


async def cmd_voice(args) -> None:
    if args.state:
        on = await calls.set_voice_recognition(args.state == 'on',
                                               args.target)
    else:
        on = (await calls.handsfree(args.target)).voice_recognition
    print(f'voice recognition: {on}')


async def cmd_monitor(args) -> None:
    print('watching for calls (ctrl-c to stop)')

    async def added():
        async for kind, call in calls.watch(args.target):
            direction = 'incoming' if call.incoming else 'outgoing'
            print(f'[{direction}] {call.who}  ({call.state})')
            print(f'  {call.path}')

    async def removed():
        async for path in calls.watch_removed(args.target):
            print(f'[ended]    {path}')

    await asyncio.gather(added(), removed())


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--json', action='store_true')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def cmd(name, fn, help_text):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(fn=fn)
        return p

    p = cmd('modems', cmd_modems, 'list modems and their state')
    p.set_defaults(target=None)

    add_target(cmd('online', cmd_online, 'power up and bring online'),
               required=False)
    add_target(cmd('list', cmd_list, 'list active calls'), required=False)
    add_target(cmd('answer', cmd_answer, 'answer the incoming call'),
               required=False)
    add_target(cmd('hangup', cmd_hangup, 'hang up all calls'),
               required=False)
    add_target(cmd('network', cmd_network, 'operator and signal'),
               required=False)
    add_target(cmd('handsfree', cmd_handsfree, 'HFP features, battery'),
               required=False)
    add_target(cmd('monitor', cmd_monitor, 'watch call events'),
               required=False)

    p = cmd('dial', cmd_dial, 'place a call')
    p.add_argument('number')
    add_target(p, required=False)
    p.add_argument('--hide-id', action='store_true')

    p = cmd('volume', cmd_volume, 'get or set call audio')
    add_target(p, required=False)
    p.add_argument('--speaker', type=int, metavar='0-100')
    p.add_argument('--mic', type=int, metavar='0-100')
    p.add_argument('--mute', choices=['on', 'off'])

    p = cmd('tones', cmd_tones, 'send DTMF digits')
    p.add_argument('digits')
    add_target(p, required=False)

    p = cmd('voice', cmd_voice, "toggle the phone's assistant")
    p.add_argument('state', nargs='?', choices=['on', 'off'])
    add_target(p, required=False)

    args = parse_args(ap, defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
