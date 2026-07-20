import binascii
from typing import Any

from .transport import TMemoryBuffer
from .protocol.base import TProtocolFactory
from .protocol.binary import TBinaryProtocolFactory


def serialize(thrift_object: Any,
              proto_factory: TProtocolFactory = TBinaryProtocolFactory()) -> bytes:
    transport = TMemoryBuffer()
    protocol = proto_factory.get_protocol(transport)
    thrift_object.write(protocol)
    protocol.write_message_end()
    return transport.getvalue()


def deserialize(thrift_object: Any, buf: bytes,
                proto_factory: TProtocolFactory = TBinaryProtocolFactory()) -> Any:
    transport = TMemoryBuffer(buf)
    protocol = proto_factory.get_protocol(transport)
    thrift_object.read(protocol)
    return thrift_object


def hexlify(byte_array: bytes, delimeter: str = ' ') -> str:
    s = binascii.hexlify(byte_array).decode('utf-8')
    return delimeter.join(a + b for a, b in zip(s[::2], s[1::2]))


def hexprint(byte_array: bytes, delimeter: str = ' ', count: int = 10) -> None:
    print("Bytes:")
    print(byte_array)

    print("\nHex:")
    g = hexlify(byte_array, delimeter).split(delimeter)
    print('\n'.join(' '.join(g[i:i + 10]) for i in range(0, len(g), 10)))
