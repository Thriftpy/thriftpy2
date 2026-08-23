"""THeader transport, wire format compatible with Apache Thrift.

See doc/specs/HeaderFormat.md in the Apache Thrift repository.
"""

from __future__ import annotations

import struct
import zlib
from io import BytesIO

from .._compat import CYTHON
from ..thrift import TApplicationException
from .base import TTransportBase, TTransportException, readall
from .memory import TMemoryBuffer

if CYTHON:
    from .memory import TCyMemoryBuffer as TMemoryBuffer  # noqa

U16 = struct.Struct("!H")
I32 = struct.Struct("!i")

HEADER_MAGIC = 0x0FFF
DEFAULT_MAX_FRAME_SIZE = 16384000
HARD_MAX_FRAME_SIZE = 0x3FFFFFFF


class THeaderClientType:
    HEADERS = 0x00

    FRAMED_BINARY = 0x01
    UNFRAMED_BINARY = 0x02

    FRAMED_COMPACT = 0x03
    UNFRAMED_COMPACT = 0x04


class THeaderSubprotocolID:
    BINARY = 0x00
    COMPACT = 0x02


class TInfoHeaderType:
    KEY_VALUE = 0x01


class THeaderTransformID:
    ZLIB = 0x01


KNOWN_READ_TRANSFORM_IDS = frozenset({THeaderTransformID.ZLIB})

WRITE_TRANSFORMS_BY_ID = {
    THeaderTransformID.ZLIB: zlib.compress,
}

_UNFRAMED_CLIENT_TYPES = (
    THeaderClientType.UNFRAMED_BINARY,
    THeaderClientType.UNFRAMED_COMPACT,
)
_FRAMED_CLIENT_TYPES = (
    THeaderClientType.FRAMED_BINARY,
    THeaderClientType.FRAMED_COMPACT,
)


# local varint helpers instead of the ones in protocol/compact.py: these
# operate on plain buffers and turn truncated input into a clean
# END_OF_FILE, compact's read_varint would raise a bare TypeError there
def _write_varint(buf, n):
    if n < 0:
        raise ValueError("varint must not be negative")
    while True:
        if n & ~0x7F == 0:
            buf.write(bytes((n,)))
            return
        buf.write(bytes(((n & 0x7F) | 0x80,)))
        n >>= 7


def _read_varint(buf):
    result = 0
    shift = 0
    while True:
        data = buf.read(1)
        if not data:
            raise TTransportException(
                TTransportException.END_OF_FILE,
                "End of frame while reading varint")
        byte = data[0]
        result |= (byte & 0x7F) << shift
        if byte >> 7 == 0:
            return result
        shift += 7


def _read_string(buf):
    size = _read_varint(buf)
    data = buf.read(size)
    if len(data) != size:
        raise TTransportException(
            TTransportException.END_OF_FILE,
            "End of frame while reading header string")
    return data


def _write_string(buf, value):
    _write_varint(buf, len(value))
    buf.write(value)


def _is_binary_header(word):
    # imported lazily, a module level import would be a cycle through
    # thriftpy2.protocol
    from ..protocol.binary import VERSION_1, VERSION_MASK
    value, = I32.unpack(word)
    return value & VERSION_MASK == VERSION_1


def _is_compact_header(word):
    from ..protocol.compact import TCompactProtocol
    return (word[0] == TCompactProtocol.PROTOCOL_ID
            and word[1] & TCompactProtocol.VERSION_MASK
            == TCompactProtocol.VERSION)


class _FrameBuffer(TMemoryBuffer):
    """Memory buffer holding the payload of one incoming frame.

    Reading past the end of the frame raises END_OF_FILE instead of
    returning short data, so the sub protocols surface truncated or corrupt
    frames as a clean transport error rather than a struct.error.
    """

    def __init__(self):
        super().__init__()
        self.remaining = 0

    def setvalue(self, value):
        super().setvalue(value)
        self.remaining = len(value)

    def read(self, sz):
        data = super().read(sz)
        self.remaining -= len(data)
        if len(data) != sz:
            raise TTransportException(
                TTransportException.END_OF_FILE,
                "End of frame while reading payload.")
        return data


class THeaderTransport(TTransportBase):
    """Frames messages with THeader headers.

    The payload of the current incoming frame lives in ``read_buffer`` and
    outgoing data is collected in ``write_buffer`` until ``flush``. Both are
    ``TMemoryBuffer`` so the Cython protocols can work on them directly.
    """

    def __init__(self, trans, allowed_client_types=(
            THeaderClientType.HEADERS,),
            default_protocol=THeaderSubprotocolID.BINARY):
        self._trans = trans
        self._client_type = THeaderClientType.HEADERS
        self._allowed_client_types = tuple(allowed_client_types)

        self.read_buffer = _FrameBuffer()
        self.write_buffer = TMemoryBuffer()
        self._pending = b""

        self._read_headers = {}
        self._write_headers = {}
        self._write_transforms = []

        self.flags = 0
        self.sequence_id = 0
        self._protocol_id = default_protocol
        self._max_frame_size = DEFAULT_MAX_FRAME_SIZE
        self._max_decompressed_size = DEFAULT_MAX_FRAME_SIZE

    def is_open(self):
        return self._trans.is_open()

    def open(self):
        return self._trans.open()

    def close(self):
        return self._trans.close()

    def get_headers(self):
        return self._read_headers

    def set_header(self, key, value):
        if not isinstance(key, bytes):
            raise ValueError("header names must be bytes")
        if not isinstance(value, bytes):
            raise ValueError("header values must be bytes")
        self._write_headers[key] = value

    def clear_headers(self):
        self._write_headers.clear()

    def add_transform(self, transform_id):
        if transform_id not in WRITE_TRANSFORMS_BY_ID:
            raise ValueError("unknown transform")
        self._write_transforms.append(transform_id)

    def set_max_frame_size(self, size):
        if not 0 < size < HARD_MAX_FRAME_SIZE:
            raise ValueError(
                "maximum frame size should be < %d and > 0"
                % HARD_MAX_FRAME_SIZE)
        self._max_frame_size = size

    def set_max_decompressed_size(self, size):
        if not 0 < size <= HARD_MAX_FRAME_SIZE:
            raise ValueError(
                "maximum decompressed size should be <= %d and > 0"
                % HARD_MAX_FRAME_SIZE)
        self._max_decompressed_size = size

    @property
    def client_type(self):
        return self._client_type

    @property
    def is_unframed(self):
        return self._client_type in _UNFRAMED_CLIENT_TYPES

    def reset_protocol_id(self, protocol_id):
        # used when answering a frame that asked for an unsupported
        # protocol, the reply must use the one the peer spoke before
        self._protocol_id = protocol_id

    @property
    def protocol_id(self):
        if self._client_type == THeaderClientType.HEADERS:
            return self._protocol_id
        if self._client_type in (THeaderClientType.FRAMED_BINARY,
                                 THeaderClientType.UNFRAMED_BINARY):
            return THeaderSubprotocolID.BINARY
        if self._client_type in (THeaderClientType.FRAMED_COMPACT,
                                 THeaderClientType.UNFRAMED_COMPACT):
            return THeaderSubprotocolID.COMPACT
        raise TTransportException(
            TTransportException.INVALID_CLIENT_TYPE,
            "Protocol ID not known for client type %d" % self._client_type)

    def _read(self, sz):
        if self._pending:
            # bytes consumed while detecting an unframed client
            data, self._pending = self._pending[:sz], self._pending[sz:]
            return data
        if self.is_unframed:
            return self._trans.read(sz)
        if self.read_buffer.remaining == 0:
            # the current frame is exhausted, fetch the next one
            self.read_frame()
            if self._pending:
                # read_frame detected an unframed client instead
                data, self._pending = self._pending[:sz], self._pending[sz:]
                return data
        return self.read_buffer.read(sz)

    def _set_client_type(self, client_type):
        if client_type not in self._allowed_client_types:
            raise TTransportException(
                TTransportException.INVALID_CLIENT_TYPE,
                "Client type %d not allowed by server." % client_type)
        self._client_type = client_type

    def read_frame(self):
        # the first word is either the length field of a framed message or
        # the first bytes of an unframed message
        first_word = readall(self._trans.read, I32.size)
        if _is_binary_header(first_word):
            self._set_client_type(THeaderClientType.UNFRAMED_BINARY)
            self._pending = first_word
            return
        if _is_compact_header(first_word):
            self._set_client_type(THeaderClientType.UNFRAMED_COMPACT)
            self._pending = first_word
            return

        frame_size, = I32.unpack(first_word)
        if frame_size < 0:
            raise TTransportException(
                TTransportException.NEGATIVE_SIZE,
                "Negative frame size.")
        if frame_size > self._max_frame_size:
            raise TTransportException(
                TTransportException.SIZE_LIMIT,
                "Frame was too large.")
        frame = readall(self._trans.read, frame_size)
        if len(frame) < I32.size:
            raise TTransportException(
                TTransportException.END_OF_FILE,
                "Frame too short to detect client type.")

        # the next word is either the version field of a binary/compact
        # message or the magic value and flags of a header message
        second_word = frame[:I32.size]
        version, = I32.unpack(second_word)
        if version >> 16 == HEADER_MAGIC:
            self._set_client_type(THeaderClientType.HEADERS)
            self.read_buffer.setvalue(self._parse_header_format(frame))
        elif _is_binary_header(second_word):
            self._set_client_type(THeaderClientType.FRAMED_BINARY)
            self.read_buffer.setvalue(frame)
        elif _is_compact_header(second_word):
            self._set_client_type(THeaderClientType.FRAMED_COMPACT)
            self.read_buffer.setvalue(frame)
        else:
            raise TTransportException(
                TTransportException.INVALID_CLIENT_TYPE,
                "Could not detect client transport type.")

    def _parse_header_format(self, frame):
        # magic, flags, sequence id and header size
        if len(frame) < 10:
            raise TTransportException(
                TTransportException.END_OF_FILE,
                "Frame too short for a header message.")
        buf = BytesIO(frame)
        buf.read(2)
        self.flags, = U16.unpack(buf.read(U16.size))
        self.sequence_id, = I32.unpack(buf.read(I32.size))

        header_length = U16.unpack(buf.read(U16.size))[0] * 4
        end_of_headers = buf.tell() + header_length
        if end_of_headers > len(frame):
            raise TTransportException(
                TTransportException.SIZE_LIMIT,
                "Header size is larger than whole frame.")

        self._protocol_id = _read_varint(buf)

        transforms = []
        transform_count = _read_varint(buf)
        for _ in range(transform_count):
            transform_id = _read_varint(buf)
            if transform_id not in KNOWN_READ_TRANSFORM_IDS:
                raise TApplicationException(
                    TApplicationException.INVALID_TRANSFORM,
                    "Unknown transform: %d" % transform_id)
            transforms.append(transform_id)
        transforms.reverse()

        headers = {}
        while buf.tell() < end_of_headers:
            header_type = _read_varint(buf)
            if header_type == TInfoHeaderType.KEY_VALUE:
                count = _read_varint(buf)
                for _ in range(count):
                    key = _read_string(buf)
                    value = _read_string(buf)
                    headers[key] = value
            else:
                # info headers are ordered oldest to newest, nothing after
                # an unknown one can be understood either
                break
        self._read_headers = headers

        payload = frame[end_of_headers:]
        for transform_id in transforms:
            payload = self._apply_read_transform(transform_id, payload)
        return payload

    def _apply_read_transform(self, transform_id, payload):
        if transform_id == THeaderTransformID.ZLIB:
            decompressor = zlib.decompressobj()
            payload = decompressor.decompress(
                payload, self._max_decompressed_size)
            if decompressor.unconsumed_tail:
                raise TTransportException(
                    TTransportException.SIZE_LIMIT,
                    "Decompressed payload exceeds maximum allowed size.")
        return payload

    def write(self, buf):
        self.write_buffer.write(buf)

    def flush(self):
        payload = self.write_buffer.getvalue()
        self.write_buffer.setvalue(b"")

        if self._client_type == THeaderClientType.HEADERS:
            frame = self._build_header_frame(payload)
        elif self._client_type in _FRAMED_CLIENT_TYPES:
            frame = I32.pack(len(payload)) + payload
        elif self._client_type in _UNFRAMED_CLIENT_TYPES:
            frame = payload
        else:
            raise TTransportException(
                TTransportException.INVALID_CLIENT_TYPE,
                "Unknown client type.")

        # the frame length field doesn't count towards the frame size
        if len(frame) - I32.size > self._max_frame_size:
            raise TTransportException(
                TTransportException.SIZE_LIMIT,
                "Attempting to send frame that is too large.")

        self._trans.write(frame)
        self._trans.flush()

    def _build_header_frame(self, payload):
        for transform_id in self._write_transforms:
            payload = WRITE_TRANSFORMS_BY_ID[transform_id](payload)

        headers = BytesIO()
        _write_varint(headers, self._protocol_id)
        _write_varint(headers, len(self._write_transforms))
        for transform_id in self._write_transforms:
            _write_varint(headers, transform_id)
        if self._write_headers:
            _write_varint(headers, TInfoHeaderType.KEY_VALUE)
            _write_varint(headers, len(self._write_headers))
            for key, value in self._write_headers.items():
                _write_string(headers, key)
                _write_string(headers, value)
            self._write_headers = {}
        padding = (4 - headers.tell() % 4) % 4
        headers.write(b"\x00" * padding)
        header_bytes = headers.getvalue()
        # the header section length is a 16 bit count of 4 byte words
        if len(header_bytes) // 4 > 0xFFFF:
            raise TTransportException(
                TTransportException.SIZE_LIMIT,
                "Headers are too large to fit in the frame header section.")

        out = BytesIO()
        out.write(I32.pack(10 + len(header_bytes) + len(payload)))
        out.write(U16.pack(HEADER_MAGIC))
        out.write(U16.pack(self.flags))
        out.write(I32.pack(self.sequence_id))
        out.write(U16.pack(len(header_bytes) // 4))
        out.write(header_bytes)
        out.write(payload)
        return out.getvalue()


class THeaderTransportFactory:
    def __init__(self, allowed_client_types=(THeaderClientType.HEADERS,),
                 default_protocol=THeaderSubprotocolID.BINARY):
        self.allowed_client_types = allowed_client_types
        self.default_protocol = default_protocol

    def get_transport(self, trans):
        return THeaderTransport(trans, self.allowed_client_types,
                                self.default_protocol)
