"""Source and packaged entrypoint share startup, shutdown and desktop handshake."""

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
from pathlib import Path

from gallery.paths import Settings


def main(argv=None):
    parser = argparse.ArgumentParser(prog='gallery')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--legacy', type=Path)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--no-watch', action='store_true')
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--no-scan', action='store_true')
    args = parser.parse_args(argv)
    if args.data:
        os.environ['GALLERY_DATA'] = str(args.data.resolve())
    if args.root:
        os.environ['GALLERY_ROOT'] = str(args.root.resolve())
    if args.legacy:
        os.environ['GALLERY_LEGACY'] = str(args.legacy.resolve())
    from dataclasses import replace
    settings = replace(Settings.environment(), watch=not args.no_watch, scan_on_start=not args.no_scan)
    settings.data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=settings.data / 'server.log', encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    if sys.stdout is None:
        sys.stdout = open(settings.data / 'console.log', 'a', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = sys.stdout
    import uvicorn

    from gallery.app import create_app
    app = create_app(settings)
    sock = socket.socket()
    sock.bind(('127.0.0.1', args.port))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host='127.0.0.1', port=port, workers=1, log_config=None, access_log=False,
                            timeout_graceful_shutdown=20)
    server = uvicorn.Server(config)
    app.state.service.shutdown_callback = lambda: setattr(server, 'should_exit', True)

    async def run():
        future = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            if future.done():
                await future
                return
            await asyncio.sleep(.01)
        descriptor = {'url': f'http://127.0.0.1:{port}', 'api_version': '1', 'version': '2.0.0',
                      'instance_id': app.state.instance_id, 'pid': os.getpid()}
        if args.ready_file:
            args.ready_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.ready_file.with_suffix('.tmp')
            temporary.write_text(json.dumps(descriptor), encoding='utf-8')
            temporary.replace(args.ready_file)
        print('GALLERY_READY ' + json.dumps(descriptor), flush=True)
        await future
    try:
        asyncio.run(run())
    finally:
        sock.close()
        if args.ready_file:
            args.ready_file.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
