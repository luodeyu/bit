
import argparse
import asyncio
import signal
import logging
from torrent import Torrent
from torrent_client import TorrentClient
from concurrent.futures import CancelledError
"""
该文件用于运行torrent的客户端，是整个项目的main函数
并通过logging模块记录并显示torrent信息
"""


def args_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', "--display", action='store_true', 
                        help='display more infomation')
    parser.add_argument('-f', '--filename', default="test1.torrent", 
                        help='fliename of .torrent')
    return parser.parse_args()


def run_client():
    args = args_parser()
    if args.display:
        logging.basicConfig(level=logging.INFO)
    # 异步IO库的套路代码
    loop = asyncio.get_event_loop()
    client = TorrentClient(Torrent(args.filename))
    task = loop.create_task(client.start())

    def signal_handler(*_):
        client.stop()
        task.cancel()

    signal.signal(signal.SIGINT, signal_handler)
    # 启动任务
    try:
        loop.run_until_complete(task)
    except CancelledError:
        pass
    except Exception:
        print("exception consumed")
    finally:
        loop.close()

if __name__ == '__main__':
    run_client()
