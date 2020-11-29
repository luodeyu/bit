from hashlib import sha1
from collections import namedtuple

import ben_decoder

TorrentFile = namedtuple('TorrentFile', ['name', 'length'])


class Torrent:  # 解析种子文件
    def __init__(self, filename):
        self.filename = filename
        self.files = []

        with open(self.filename, 'rb') as f:
            meta_info = f.read()
            self.meta_info = ben_decoder.Decoder(meta_info).decode()
            info = ben_decoder.Encoder(self.meta_info[b'info']).encode()
            self.info_hash = sha1(info).digest()
            self._identify_files()

    def _identify_files(self):
        """
        Identifies the files included in this torrent
        """
        if self.multi_file:
            # TODO Add support for multi-file torrents
            raise RuntimeError('Multi-file torrents is not supported!')
        self.files.append(
            TorrentFile(
                self.meta_info[b'info'][b'name'].decode('utf-8'),
                self.meta_info[b'info'][b'length']))

    @property
    def announce(self) -> str:

        return self.meta_info[b'announce'].decode('utf-8')

    @property
    def multi_file(self) -> bool:

        # If the info dict contains a files element then it is a multi-file
        return b'files' in self.meta_info[b'info']

    @property
    def piece_length(self) -> int:

        return self.meta_info[b'info'][b'piece length']

    @property
    def total_size(self) -> int:

        if self.multi_file:
            raise RuntimeError('Multi-file torrents is not supported!')
        return self.files[0].length

    @property
    def pieces(self):

        data = self.meta_info[b'info'][b'pieces']
        pieces = []
        offset = 0
        length = len(data)

        while offset < length:
            pieces.append(data[offset:offset + 20])
            offset += 20
        return pieces

    @property
    def output_file(self):
        return self.meta_info[b'info'][b'name'].decode('utf-8')

    def __str__(self):
        return 'Filename: {0}\n' \
               'File length: {1}\n' \
               'Announce URL: {2}\n' \
               'Hash: {3}'.format(self.meta_info[b'info'][b'name'],
                                  self.meta_info[b'info'][b'length'],
                                  self.meta_info[b'announce'],
                                  self.info_hash)
