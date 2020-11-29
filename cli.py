
import argparse
import asyncio
import signal
import logging

from concurrent.futures import CancelledError

from torrent import Torrent
from client import TorrentClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('torrent', help='.torrent file')
    parser.add_argument('-v', '--verbose', action='store_true', help='display more infomation')
    args = parser.parse_args()
    print(args)
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    client = TorrentClient(Torrent(args.torrent))
    task = loop.create_task(client.start())

    def signal_handler(*_):
        client.stop()
        task.cancel()

    signal.signal(signal.SIGINT, signal_handler)

    try:
        loop.run_until_complete(task)
    except CancelledError:
        pass


if __name__ == '__main__':
    main()
