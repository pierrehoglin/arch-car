#!/usr/bin/env python3
"""
Run the carlib daemon.

    carlibd                     # Unix socket only
    carlibd --tcp               # socket AND localhost, for a browser UI
    carlibd --tcp --port 8099

One process owns the runtime state and runs the source supervisor.
Everything else -- the CLIs, a web UI -- talks to it.

The Unix socket is always served, because that is what the CLIs use.
--tcp adds a second listener rather than replacing it.

TCP binds 127.0.0.1 only: the hotspot runs on this machine, and
passengers should not be able to change stations.
"""

import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path

DEFAULT_PORT = 8099


def socket_path() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR')
    return Path(base or '/tmp') / 'carlib.sock'


async def serve_both(sock: Path, host: str, port: int,
                     log_level: str) -> None:
    """
    Serve the same app on a Unix socket and a TCP port at once.

    The CLIs use the socket; a browser UI needs TCP. uvicorn binds one
    address per Server instance, so this runs two against the same
    application.

    Only one may run the lifespan hook. The second is created with
    lifespan='off' -- otherwise the source supervisor would start
    twice and the two copies would fight over the same state, which is
    the exact problem the daemon exists to prevent.

    Delete this function and the --tcp argument to go back to a socket
    only.
    """
    import uvicorn

    socket_server = uvicorn.Server(uvicorn.Config(
        'carlib.api.main:app', uds=str(sock), log_level=log_level))

    tcp_server = uvicorn.Server(uvicorn.Config(
        'carlib.api.main:app', host=host, port=port,
        log_level=log_level, lifespan='off'))

    socket_task = asyncio.create_task(socket_server.serve())

    # Wait for startup to finish before opening the port. Starting
    # both together leaves a window where a TCP request could arrive
    # before the lifespan hook has taken state into memory, and that
    # request would read the files instead.
    for _ in range(100):
        if socket_server.started:
            break
        await asyncio.sleep(0.05)

    await asyncio.gather(socket_task, tcp_server.serve())


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--socket', default=None,
                    help='Unix socket path (default '
                         '$XDG_RUNTIME_DIR/carlib.sock)')
    ap.add_argument('--tcp', action='store_true',
                    help='also listen on localhost, for a browser UI; '
                         'the Unix socket is served either way')
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

    sock = Path(args.socket) if args.socket else socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    # A socket left behind by a crash would stop uvicorn binding.
    if sock.exists():
        try:
            sock.unlink()
        except OSError:
            pass

    print(f'listening on {sock}', file=sys.stderr)

    if not args.tcp:
        uvicorn.run('carlib.api.main:app', uds=str(sock),
                    log_level=args.log_level)
        return 0

    # Both listeners. uvicorn binds one address per Server, so serving
    # a socket and a port at once means two of them sharing the app.
    #
    # To drop TCP later: delete this branch, the --tcp/--host/--port
    # arguments, and serve_both() below. Nothing else depends on it --
    # the socket path above is the same either way.
    print(f'listening on http://{args.host}:{args.port}',
          file=sys.stderr)
    asyncio.run(serve_both(sock, args.host, args.port, args.log_level))
    return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
