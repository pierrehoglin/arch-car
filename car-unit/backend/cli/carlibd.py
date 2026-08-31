#!/usr/bin/env python3
"""
Run the carlib daemon.

    carlibd                     # Unix socket, the usual case
    carlibd --tcp               # also listen on localhost for a browser UI
    carlibd --port 8099

One process owns the runtime state and runs the source supervisor.
Everything else -- the CLIs, a web UI -- talks to it over the socket.

The Unix socket keeps CLI traffic off the network entirely. --tcp
binds 127.0.0.1 only: the hotspot runs on this machine, and passengers
should not be able to change stations.
"""

import os
import sys
import logging
import argparse
from pathlib import Path

DEFAULT_PORT = 8099


def socket_path() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR')
    return Path(base or '/tmp') / 'carlib.sock'


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--socket', default=None,
                    help='Unix socket path (default '
                         '$XDG_RUNTIME_DIR/carlib.sock)')
    ap.add_argument('--tcp', action='store_true',
                    help='listen on localhost as well, for a browser UI')
    ap.add_argument('--host', default='127.0.0.1',
                    help='TCP host; leave as localhost unless you '
                         'have thought about who is on your hotspot')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--log-level', default='info',
                    choices=['critical', 'error', 'warning', 'info',
                             'debug'])
    args = ap.parse_args()

    try:
        import uvicorn
    except ImportError:
        print('uvicorn is not installed', file=sys.stderr)
        print('  uv sync --extra api', file=sys.stderr)
        return 1

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S')

    config: dict = {
        'app': 'carlib.api.main:app',
        'log_level': args.log_level,
    }

    if args.tcp:
        config['host'] = args.host
        config['port'] = args.port
        print(f'listening on http://{args.host}:{args.port}',
              file=sys.stderr)
    else:
        sock = Path(args.socket) if args.socket else socket_path()
        sock.parent.mkdir(parents=True, exist_ok=True)
        # A socket left behind by a crash would stop uvicorn binding.
        if sock.exists():
            try:
                sock.unlink()
            except OSError:
                pass
        config['uds'] = str(sock)
        print(f'listening on {sock}', file=sys.stderr)

    uvicorn.run(**config)
    return 0


if __name__ == '__main__':
    sys.exit(main())
