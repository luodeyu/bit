import aiohttp
import random
import logging
import socket
import ben_decoder
from struct import unpack
from urllib.parse import urlencode


class Tracker:

    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = _calculate_peer_id()
        self.http_client = aiohttp.ClientSession()

    async def connect(self,
                      first: bool = None,
                      uploaded: int = 0,
                      downloaded: int = 0):

        params = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.peer_id,
            'port': 6889,
            'uploaded': uploaded,
            'downloaded': downloaded,
            'left': self.torrent.total_size - downloaded,
            'compact': 1}
        if first:
            params['event'] = 'started'

        url = self.torrent.announce + '?' + urlencode(params)
        logging.info('Connecting to tracker at: ' + url)

        async with self.http_client.get(url) as response:
            if not response.status == 200:
                raise ConnectionError('Unable to connect to tracker: status code {}'.format(response.status))
            data = await response.read()
            print(ben_decoder.Decoder(data).decode())
            self.raise_for_error(data)
            return TrackersResponse(ben_decoder.Decoder(data).decode())

    def close(self):
        self.http_client.close()

    def raise_for_error(self, tracker_response):

        try:
            # a tracker response containing an error will have a utf-8 message only.
            # see: https://wiki.theory.org/index.php/BitTorrentSpecification#Tracker_Response
            message = tracker_response.decode("utf-8")
            if "failure" in message:
                raise ConnectionError('Unable to connect to tracker: {}'.format(message))

        # a successful tracker response will have non-uncicode data, so it's a safe to bet ignore this exception.
        except UnicodeDecodeError:
            pass

    def _construct_tracker_parameters(self):

        return {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.peer_id,
            'port': 6889,
            # TODO Update stats when communicating with tracker
            'uploaded': 0,
            'downloaded': 0,
            'left': 0,
            'compact': 1}


class TrackersResponse:

    def __init__(self, response: dict):
        self.response = response

    @property
    def failure(self):

        if b'failure reason' in self.response:
            return self.response[b'failure reason'].decode('utf-8')
        return None

    @property
    def interval(self) -> int:

        return self.response.get(b'interval', 0)

    @property
    def complete(self) -> int:

        return self.response.get(b'complete', 0)

    @property
    def incomplete(self) -> int:

        return self.response.get(b'incomplete', 0)

    @property
    def peers(self):

        peers = self.response[b'peers']
        if type(peers) == list:
            # TODO Implement support for dictionary peer list
            logging.debug('Dictionary model peers are returned by tracker')
            raise NotImplementedError()
        else:
            logging.debug('Binary model peers are returned by tracker')

            peers = [peers[i:i + 6] for i in range(0, len(peers), 6)]

            # Convert the encoded address to a list of tuples
            return [(socket.inet_ntoa(p[:4]), _decode_port(p[4:]))
                    for p in peers]

    def __str__(self):
        return "incomplete: {incomplete}\n" \
               "complete: {complete}\n" \
               "interval: {interval}\n" \
               "peers: {peers}\n".format(
            incomplete=self.incomplete,
            complete=self.complete,
            interval=self.interval,
            peers=", ".join([x for (x, _) in self.peers]))


def _calculate_peer_id():
    return '-PC0001-' + ''.join(
        [str(random.randint(0, 9)) for _ in range(12)])


def _decode_port(port):
    # Convert from C style big-endian encoded as unsigned short
    return unpack(">H", port)[0]
