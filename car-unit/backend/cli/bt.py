#!/usr/bin/env python3
"""
Bluetooth: the service, pairing, and the devices on it.

    bt                              status, and every known device
    bt start | stop                 bluetooth.service
    bt pairing-mode [--for 120]     scan, and be findable, for a while
    bt stop-pairing                 close the window early
    bt pair ADDRESS                 pair with a device from the car's side
    bt pairing [yes|no]             show or answer a waiting confirmation
    bt connect | disconnect ADDRESS
    bt forget ADDRESS               unpair and remove

Goes through the daemon, which has to be running. Pairing can only
work there: the agent that answers BlueZ has to stay registered, and
scanning stops the moment the process that started it exits.

Pairing mode is one window -- scanning, discoverable and pairable
together. Outside it the car is invisible and accepts no new pairings,
but phones already paired still reconnect.

To pair a phone: run `bt pairing-mode`, pick the car on the phone, and
confirm the code when it appears here and on the phone.
"""

import sys
import asyncio
import argparse

from carlib.api.client import bluetooth
from carlib.core.output import (run, emit_json, global_flags, parse_args,
                                DEVICE_ICONS, GLYPH)


# --- Showing ----------------------------------------------------------------

def line(device: dict) -> str:
    icon = DEVICE_ICONS.get(device.get('icon', ''), GLYPH['bluetooth'])
    state = ('connected' if device.get('connected')
             else 'paired' if device.get('paired') else 'nearby')

    rssi = device.get('rssi')
    signal = f'{rssi:>4} dBm' if rssi is not None else ' ' * 8
    battery = device.get('battery')
    charge = f'{battery:>3}%' if battery is not None else '    '

    # Handsfree, Phonebook, Messages: what the car can do with it.
    uuids = [u.lower() for u in device.get('uuids') or []]
    caps = ''.join([
        'H' if any(u.startswith('0000111f') for u in uuids) else '-',
        'P' if any(u.startswith('0000112f') for u in uuids) else '-',
        'M' if any(u.startswith('00001132') for u in uuids) else '-',
    ])

    return (f'{icon}  {device["name"][:24]:<24}  {device["address"]}  '
            f'{state:<9}  {signal}  {charge}  {caps}')


def show(state: dict) -> None:
    adapter = state['adapter']

    if not adapter['service_active']:
        print('bluetooth.service is stopped')
        print('  bt start', file=sys.stderr)
        return

    window = state['window']
    flags = [f'{"on" if adapter["powered"] else "off"}']
    if window['open']:
        flags.append(f'pairing for {window["seconds_left"]}s')

    print(f'{adapter["name"]}  {adapter["address"]}  {", ".join(flags)}')
    print()

    devices = state['devices']
    if not devices:
        print('  no devices')
        if not window['open']:
            print('  bt pairing-mode  to find some', file=sys.stderr)
        return

    for device in devices:
        print(f'  {line(device)}')

    attempt = state.get('attempt')
    if attempt and attempt['state'] == 'failed':
        print(f'\nlast pairing failed: {attempt["error"]}', file=sys.stderr)


# --- Confirming -------------------------------------------------------------

async def confirm(request: dict) -> None:
    """
    Ask at the terminal, and send the answer.

    input() blocks, so it runs in a thread. BlueZ waits about thirty
    seconds; an answer after that reports as unanswered rather than
    pretending it landed.
    """
    name = request.get('name') or request.get('address') or 'a device'

    if request.get('passkey'):
        print(f'\n{name} wants to pair')
        print(f'  code  {request["passkey"]}')
        print('  check the phone shows the same code')
        prompt = '  confirm? [y/N] '
    else:
        print(f'\n{name} wants to pair (no code to compare)')
        prompt = '  allow? [y/N] '

    loop = asyncio.get_running_loop()
    reply = await loop.run_in_executor(None, input, prompt)
    accept = reply.strip().lower() in ('y', 'yes')

    result = await bluetooth.answer(accept)
    if not result.get('answered'):
        print('  too late -- the phone gave up waiting', file=sys.stderr)
    elif accept:
        print('  confirmed')
    else:
        print('  refused')


async def follow(until_done=None) -> dict:
    """
    Watch the daemon, printing devices as they appear and prompting
    for any confirmation.

    Returns the last state seen. Stops when `until_done(state)` says
    so, or when the pairing window closes.
    """
    seen: set[str] = set()
    asked: set[str] = set()
    state: dict = {}

    while True:
        state = await bluetooth.status()

        for device in state['devices']:
            if device['address'] not in seen:
                seen.add(device['address'])
                print(f'  {line(device)}')

        request = await bluetooth.pending()
        if request:
            key = f'{request.get("device")}:{request.get("passkey")}'
            if key not in asked:
                asked.add(key)
                await confirm(request)

        if until_done is not None and until_done(state):
            return state
        if until_done is None and not state['window']['open']:
            return state

        await asyncio.sleep(1)


# --- Commands ---------------------------------------------------------------

async def cmd_status(args) -> None:
    state = await bluetooth.status()
    if args.json:
        emit_json(state)
        return
    show(state)


async def cmd_start(args) -> None:
    await bluetooth.service(True)
    await cmd_status(args)


async def cmd_stop(args) -> None:
    """oFono is PartOf bluetooth.service, so calls go with it."""
    await bluetooth.service(False)
    await cmd_status(args)


async def cmd_pairing_mode(args) -> None:
    window = await bluetooth.pairing_mode(args.seconds)
    print(f'pairing for {window["seconds_left"]}s -- the car is findable '
          f'and scanning')
    print('pick it on the phone, or `bt pair ADDRESS` in another '
          'terminal', file=sys.stderr)
    print('ctrl-c to stop early', file=sys.stderr)
    print()

    try:
        await follow()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bluetooth.stop_pairing_mode()
        print('\nwindow closed')


async def cmd_stop_pairing(args) -> None:
    await bluetooth.stop_pairing_mode()
    print('window closed')


async def cmd_pair(args) -> None:
    """
    Pair from the car's side, following it to the end.

    The confirmation arrives here as it would for a phone pairing with
    the car -- both go through the same agent.
    """
    address = args.address.upper()
    await bluetooth.pair(address)
    print(f'pairing with {address}')

    def finished(state: dict) -> bool:
        attempt = state.get('attempt') or {}
        return (attempt.get('address') == address
                and attempt.get('state') in ('paired', 'failed'))

    state = await follow(finished)
    attempt = state.get('attempt') or {}

    if attempt.get('state') == 'paired':
        print('paired and trusted')
    else:
        print(f'failed: {attempt.get("error", "unknown")}', file=sys.stderr)


async def cmd_pairing(args) -> None:
    """Show, or answer, the confirmation that is waiting."""
    if args.answer is None:
        request = await bluetooth.pending()
        if args.json:
            emit_json(request)
            return
        if not request:
            print('nothing waiting')
            return
        await confirm(request)
        return

    result = await bluetooth.answer(args.answer == 'yes')
    if result.get('answered'):
        print('confirmed' if args.answer == 'yes' else 'refused')
    else:
        print('nothing was waiting', file=sys.stderr)


async def cmd_connect(args) -> None:
    device = await bluetooth.connect(args.address)
    print(line(device))


async def cmd_disconnect(args) -> None:
    device = await bluetooth.disconnect(args.address)
    print(line(device))


async def cmd_forget(args) -> None:
    await bluetooth.forget(args.address)
    print(f'forgot {args.address.upper()}')
    print('the phone may still list the car -- forget it there too '
          'before pairing again', file=sys.stderr)


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('status', parents=[common],
                       help='service, adapter and every known device')
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser('start', parents=[common],
                       help='start bluetooth.service')
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser('stop', parents=[common],
                       help='stop bluetooth.service (and HFP with it)')
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser('pairing-mode', parents=[common],
                       help='scan, and be findable, for a while')
    p.set_defaults(fn=cmd_pairing_mode)
    p.add_argument('--for', dest='seconds', type=int, default=120,
                   help='seconds (10 to 600, default 120)')

    p = sub.add_parser('stop-pairing', parents=[common],
                       help='close the pairing window early')
    p.set_defaults(fn=cmd_stop_pairing)

    p = sub.add_parser('pair', parents=[common],
                       help='pair with a device from the car')
    p.set_defaults(fn=cmd_pair)
    p.add_argument('address')

    p = sub.add_parser('pairing', parents=[common],
                       help='show or answer a waiting confirmation')
    p.set_defaults(fn=cmd_pairing)
    p.add_argument('answer', nargs='?', choices=('yes', 'no'))

    for name, fn, text in (
            ('connect', cmd_connect, 'connect a paired device'),
            ('disconnect', cmd_disconnect, 'disconnect a device'),
            ('forget', cmd_forget, 'unpair and remove a device')):
        p = sub.add_parser(name, parents=[common], help=text)
        p.set_defaults(fn=fn)
        p.add_argument('address')

    args = parse_args(ap, 'status', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
