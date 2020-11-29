

import asyncio
import logging
import struct
from asyncio import Queue
from concurrent.futures import CancelledError
import bitstring


BLOCK_SIZE = 2**14


# Message基类，定义交互message格式
class Message:

    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9
    Handshake = None
    KeepAlive = None

    def encode(self) -> bytes:

        pass

    @classmethod
    def decode(cls, data: bytes):
        pass


class Handshake(Message):

    length = 49 + 19

    def __init__(self, info_hash: bytes, peer_id: bytes):

        if isinstance(info_hash, str):
            info_hash = info_hash.encode('utf-8')
        if isinstance(peer_id, str):
            peer_id = peer_id.encode('utf-8')
        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self) -> bytes:

        return struct.pack(
            '>B19s8x20s20s',
            19,                         
            b'BitTorrent protocol',                               
            self.info_hash,             
            self.peer_id)               

    @classmethod
    def decode(cls, data: bytes):

        logging.debug('Decoding Handshake of length: {length}'.format(
            length=len(data)))
        if len(data) < (49 + 19):
            return None
        parts = struct.unpack('>B19s8x20s20s', data)
        return cls(info_hash=parts[2], peer_id=parts[3])

    def __str__(self):
        return 'Handshake'


class KeepAlive(Message):

    def __str__(self):
        return 'KeepAlive'


class BitField(Message):

    def __init__(self, data):
        self.bitfield = bitstring.BitArray(bytes=data)

    def encode(self) -> bytes:

        bits_length = len(self.bitfield)
        return struct.pack('>Ib' + str(bits_length) + 's',
                           1 + bits_length,
                           Message.BitField,
                           self.bitfield)

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack('>I', data[:4])[0]
        logging.debug('Decoding BitField of length: {length}'.format(
            length=message_length))

        parts = struct.unpack('>Ib' + str(message_length - 1) + 's', data)
        return cls(parts[2])

    def __str__(self):
        return 'BitField'


class Interested(Message):

    def encode(self) -> bytes:

        return struct.pack('>Ib',
                           1,
                           Message.Interested)

    def __str__(self):
        return 'Interested'


class NotInterested(Message):

    def __str__(self):
        return 'NotInterested'


class Choke(Message):

    def __str__(self):
        return 'Choke'


class Unchoke(Message):

    def __str__(self):
        return 'Unchoke'


class Have(Message):

    def __init__(self, index: int):
        self.index = index

    def encode(self):
        return struct.pack('>IbI',
                           5,
                           Message.Have,
                           self.index)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Have of length: {length}'.format(
            length=len(data)))
        index = struct.unpack('>IbI', data)[2]
        return cls(index)

    def __str__(self):
        return 'Have'


class Request(Message):

    def __init__(self, index: int, begin: int, length: int = BLOCK_SIZE):

        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           Message.Request,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Request of length: {length}'.format(
            length=len(data)))
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Request'


class Piece(Message):

    length = 9

    def __init__(self, index: int, begin: int, block: bytes):

        self.index = index
        self.begin = begin
        self.block = block

    def encode(self):
        message_length = Piece.length + len(self.block)
        return struct.pack('>IbII' + str(len(self.block)) + 's',
                           message_length,
                           Message.Piece,
                           self.index,
                           self.begin,
                           self.block)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Piece of length: {length}'.format(
            length=len(data)))
        length = struct.unpack('>I', data[:4])[0]
        parts = struct.unpack('>IbII' + str(length - Piece.length) + 's',
                              data[:length+4])
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Piece'


class Cancel(Message):

    def __init__(self, index, begin, length: int = BLOCK_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           Message.Cancel,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Cancel of length: {length}'.format(
            length=len(data)))
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Cancel'


class PeersConnection:
    def __init__(self, queue: Queue, info_hash,
                 peer_id, piece_manager, on_block_cb=None):
        self.my_state = []
        self.peer_state = []
        self.queue = queue
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.remote_id = None
        self.writer = None
        self.reader = None
        self.piece_manager = piece_manager
        self.on_block_cb = on_block_cb
        self.future = asyncio.ensure_future(self._start())

    async def _start(self):
        while 'stopped' not in self.my_state:
            ip, port = await self.queue.get()
            logging.info('Got assigned peer with: {ip}'.format(ip=ip))

            try:
                self.reader, self.writer = await asyncio.open_connection(
                    ip, port)  # 异步TCP请求
                logging.info('Connection open to peer: {ip}'.format(ip=ip))

                buffer = await self._handshake()
                self.my_state.append('choked')

                await self._send_interested()
                self.my_state.append('interested')

                async for message in StreamGetter(self.reader, buffer):
                    if 'stopped' in self.my_state:
                        break
                    if type(message) is BitField:
                        self.piece_manager.add_peer(self.remote_id,
                                                    message.bitfield)
                    elif type(message) is Interested:
                        self.peer_state.append('interested')
                    elif type(message) is NotInterested:
                        if 'interested' in self.peer_state:
                            self.peer_state.remove('interested')
                    elif type(message) is Choke:
                        self.my_state.append('choked')
                    elif type(message) is Unchoke:
                        if 'choked' in self.my_state:
                            self.my_state.remove('choked')
                    elif type(message) is Have:
                        self.piece_manager.update_peer(self.remote_id,
                                                       message.index)
                    elif type(message) is KeepAlive:
                        pass
                    elif type(message) is Piece:
                        self.my_state.remove('pending_request')
                        self.on_block_cb(
                            peer_id=self.remote_id,
                            piece_index=message.index,
                            block_offset=message.begin,
                            data=message.block)
                    elif type(message) is Request or type(message) is Cancel:
                        pass

                    if 'choked' not in self.my_state:
                        if 'interested' in self.my_state:
                            if 'pending_request' not in self.my_state:
                                self.my_state.append('pending_request')
                                await self._request_piece()

            except PeersProtocolError as e:
                logging.exception('Protocol error')
            except (ConnectionRefusedError, TimeoutError):
                logging.warning('Unable to connect to peer')
            except (ConnectionResetError, CancelledError):
                logging.warning('Connection closed')
            except Exception as e:
                logging.exception('An error occurred')
                self.cancel()
                raise e
            self.cancel()

    def cancel(self):
        logging.info('Closing peer {id}'.format(id=self.remote_id))
        if not self.future.done():
            self.future.cancel()
        if self.writer:
            self.writer.close()

        self.queue.task_done()

    def stop(self):
        self.my_state.append('stopped')
        if not self.future.done():
            self.future.cancel()

    async def _request_piece(self):
        block = self.piece_manager.next_request(self.remote_id)
        if block:
            message = Request(block.piece, block.offset, block.length).encode()

            logging.debug('Requesting block {block} for piece {piece} '
                          'of {length} bytes from peer {peer}'.format(
                            piece=block.piece,
                            block=block.offset,
                            length=block.length,
                            peer=self.remote_id))

            self.writer.write(message)
            await self.writer.drain()

    async def _handshake(self):
        self.writer.write(Handshake(self.info_hash, self.peer_id).encode())
        await self.writer.drain()

        buf = b''
        tries = 1
        while len(buf) < Handshake.length and tries < 10:
            tries += 1
            buf = await self.reader.read(StreamGetter.CHUNK_SIZE)

        response = Handshake.decode(buf[:Handshake.length])
        if not response:
            raise PeersProtocolError('Unable receive and parse a handshake')
        if not response.info_hash == self.info_hash:
            raise PeersProtocolError('Handshake with invalid info_hash')

        self.remote_id = response.peer_id
        logging.info('Handshake successful !')

        return buf[Handshake.length:]

    async def _send_interested(self):
        message = Interested()
        logging.debug('Sending message: {type}'.format(type=message))
        self.writer.write(message.encode())
        await self.writer.drain()


class StreamGetter:
    CHUNK_SIZE = 10*1024

    def __init__(self, reader, initial: bytes=None):
        self.reader = reader
        self.buffer = initial if initial else b''

    async def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            try:
                data = await self.reader.read(StreamGetter.CHUNK_SIZE)
                if data:
                    self.buffer += data
                    message = self.parse()
                    if message:
                        return message
                else:
                    logging.debug('No data read from stream')
                    if self.buffer:
                        message = self.parse()
                        if message:
                            return message
                    raise StopAsyncIteration()
            except ConnectionResetError:
                logging.debug('Connection closed by peer')
                raise StopAsyncIteration()
            except CancelledError:
                raise StopAsyncIteration()
            except StopAsyncIteration as e:
                # Cath to stop logging
                raise e
            except Exception:
                logging.exception('Error when iterating over stream!')
                raise StopAsyncIteration()
        raise StopAsyncIteration()

    def parse(self):

        header_length = 4

        if len(self.buffer) > 4:
            message_length = struct.unpack('>I', self.buffer[0:4])[0]

            if message_length == 0:
                return KeepAlive()

            if len(self.buffer) >= message_length:
                message_id = struct.unpack('>b', self.buffer[4:5])[0]

                def _consume():
                    self.buffer = self.buffer[header_length + message_length:]

                def _data():
                    return self.buffer[:header_length + message_length]

                if message_id is Message.BitField:
                    data = _data()
                    _consume()
                    return BitField.decode(data)
                elif message_id is Message.Interested:
                    _consume()
                    return Interested()
                elif message_id is Message.NotInterested:
                    _consume()
                    return NotInterested()
                elif message_id is Message.Choke:
                    _consume()
                    return Choke()
                elif message_id is Message.Unchoke:
                    _consume()
                    return Unchoke()
                elif message_id is Message.Have:
                    data = _data()
                    _consume()
                    return Have.decode(data)
                elif message_id is Message.Piece:
                    data = _data()
                    _consume()
                    return Piece.decode(data)
                elif message_id is Message.Request:
                    data = _data()
                    _consume()
                    return Request.decode(data)
                elif message_id is Message.Cancel:
                    data = _data()
                    _consume()
                    return Cancel.decode(data)
                else:
                    logging.info('Unsupported message!')
            else:
                logging.debug('Not enough in buffer in order to parse')
        return None


class PeersProtocolError(BaseException):
    """协议交互出现错误时抛出该异常"""

