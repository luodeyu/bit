
from collections import OrderedDict

"""
该文件主要帮助完成torrent文件的编解码
根据不同的数据类型,完成不同的编解码规则
"""


INTEGER = b'i'
LIST = b'l'
DICT = b'd'
END = b'e'
STRING_SEPARATOR = b':'


class Decoder:
    def __init__(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError('Argument "data" must be of type bytes')
        self._data = data
        self._index = 0

    def decode(self):
        c = self._peek()
        if c is None:
            raise EOFError('Unexpected end-of-file')
        elif c == INTEGER:
            self._consume()  
            return self._decode_int()
        elif c == LIST:
            self._consume() 
            return self._decode_list()
        elif c == DICT:
            self._consume()  
            return self._decode_dict()
        elif c == END:
            return None
        elif c in b'01234567899':
            return self._decode_string()
        else:
            raise RuntimeError('Invalid token read at {0}'.format(
                str(self._index)))

    def _peek(self):
        if self._index + 1 >= len(self._data):
            return None
        return self._data[self._index:self._index + 1]

    def _consume(self) -> bytes:
        self._index += 1

    def _read(self, length: int) -> bytes:
        if self._index + length > len(self._data):
            raise IndexError('Cannot read {0} bytes from current position {1}'
                             .format(str(length), str(self._index)))
        res = self._data[self._index:self._index+length]
        self._index += length
        return res

    def _read_until(self, token: bytes) -> bytes:
        try:
            occurrence = self._data.index(token, self._index)
            result = self._data[self._index:occurrence]
            self._index = occurrence + 1
            return result
        except ValueError:
            raise RuntimeError('Unable to find token {0}'.format(
                str(token)))

    def _decode_int(self):
        return int(self._read_until(END))

    def _decode_list(self):
        res = []
        while self._data[self._index: self._index + 1] != END:
            res.append(self.decode())
        self._consume()
        return res

    def _decode_dict(self):
        res = OrderedDict()
        while self._data[self._index: self._index + 1] != END:
            key = self.decode()
            obj = self.decode()
            res[key] = obj
        self._consume()
        return res

    def _decode_string(self):
        bytes_to_read = int(self._read_until(STRING_SEPARATOR))
        data = self._read(bytes_to_read)
        return data


class Encoder:
    def __init__(self, data):
        self._data = data

    def encode(self) -> bytes:
        return self.encode_next(self._data)

    def encode_next(self, data):
        if type(data) == str:
            return self._encode_string(data)
        elif type(data) == int:
            return self._encode_int(data)
        elif type(data) == list:
            return self._encode_list(data)
        elif type(data) == dict or type(data) == OrderedDict:
            return self._encode_dict(data)
        elif type(data) == bytes:
            return self._encode_bytes(data)
        else:
            return None

    def _encode_int(self, value):
        return str.encode('i' + str(value) + 'e')

    def _encode_string(self, value: str):
        res = str(len(value)) + ':' + value
        return str.encode(res)

    def _encode_bytes(self, value: str):
        result = bytearray()
        result += str.encode(str(len(value)))
        result += b':'
        result += value
        return result

    def _encode_list(self, data):
        result = bytearray('l', 'utf-8')
        result += b''.join([self.encode_next(item) for item in data])
        result += b'e'
        return result

    def _encode_dict(self, data: dict) -> bytes:
        result = bytearray('d', 'utf-8')
        for k, v in data.items():
            key = self.encode_next(k)
            value = self.encode_next(v)
            if key and value:
                result += key
                result += value
            else:
                raise RuntimeError('Bad dict')
        result += b'e'
        return result
