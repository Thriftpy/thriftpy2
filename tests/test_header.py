import contextlib
import socket
import struct
import threading
import time
import zlib
from os import path

import pytest

import thriftpy2
from thriftpy2.protocol import (
    TBinaryProtocolFactory,
    TCompactProtocolFactory,
    THeaderProtocol,
    THeaderProtocolFactory,
)
from thriftpy2.rpc import client_context, make_server
from thriftpy2.server import TServer
from thriftpy2.thrift import (
    TApplicationException,
    TMessageType,
    TPayload,
    TProcessor,
)
from thriftpy2.transport import (
    TBufferedTransportFactory,
    TFramedTransportFactory,
    TMemoryBuffer,
    TServerSocket,
    TTransportException,
)
from thriftpy2.transport.header import (
    HEADER_MAGIC,
    THeaderClientType,
    THeaderSubprotocolID,
    THeaderTransformID,
    THeaderTransport,
)

addressbook = thriftpy2.load(path.join(path.dirname(__file__),
                                       "addressbook.thrift"))

ALL_CLIENT_TYPES = (
    THeaderClientType.HEADERS,
    THeaderClientType.FRAMED_BINARY,
    THeaderClientType.UNFRAMED_BINARY,
    THeaderClientType.FRAMED_COMPACT,
    THeaderClientType.UNFRAMED_COMPACT,
)


class Dispatcher:
    def __init__(self):
        self.registry = {}

    def add(self, person):
        if person.name in self.registry:
            return False
        self.registry[person.name] = person
        return True

    def get(self, name):
        if name not in self.registry:
            raise addressbook.PersonNotExistsError()
        return self.registry[name]

    def remove(self, name):
        if name not in self.registry:
            raise addressbook.PersonNotExistsError()
        del self.registry[name]
        return True


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[-1]


@contextlib.contextmanager
def header_server(proto_factory):
    port = free_port()
    server = make_server(
        addressbook.AddressBookService,
        Dispatcher(),
        host="127.0.0.1",
        port=port,
        proto_factory=proto_factory,
        trans_factory=TBufferedTransportFactory(),
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield port
    finally:
        server.close()
        server.trans.close()
        thread.join(timeout=1)


def exercise(client):
    dennis = addressbook.Person(name="Dennis Ritchie",
                                phones=[addressbook.PhoneNumber(
                                    type=addressbook.PhoneType.MOBILE,
                                    number="123")])
    assert client.add(dennis)
    assert not client.add(dennis)
    assert client.get("Dennis Ritchie") == dennis
    assert client.add(addressbook.Person(name=""))
    with pytest.raises(addressbook.PersonNotExistsError):
        client.get("nobody")
    assert client.remove("Dennis Ritchie")
    with pytest.raises(addressbook.PersonNotExistsError):
        client.remove("Dennis Ritchie")


@pytest.mark.parametrize("sub_protocol", [THeaderSubprotocolID.BINARY,
                                          THeaderSubprotocolID.COMPACT])
def test_header_client_and_server(sub_protocol):
    with header_server(THeaderProtocolFactory()) as port:
        with client_context(
            addressbook.AddressBookService, "127.0.0.1", port,
            proto_factory=THeaderProtocolFactory(
                default_protocol=sub_protocol),
            trans_factory=TBufferedTransportFactory(),
        ) as client:
            exercise(client)


def test_header_transforms_and_headers():
    with header_server(THeaderProtocolFactory()) as port:
        with client_context(
            addressbook.AddressBookService, "127.0.0.1", port,
            proto_factory=THeaderProtocolFactory(),
            trans_factory=TBufferedTransportFactory(),
        ) as client:
            proto = client._iprot
            proto.add_transform(THeaderTransformID.ZLIB)
            proto.set_header(b"trace", b"abc")
            exercise(client)


@pytest.mark.parametrize("proto_factory,trans_factory", [
    (TBinaryProtocolFactory(), TFramedTransportFactory()),
    (TBinaryProtocolFactory(), TBufferedTransportFactory()),
    (TCompactProtocolFactory(), TFramedTransportFactory()),
    (TCompactProtocolFactory(), TBufferedTransportFactory()),
], ids=["framed-binary", "unframed-binary",
        "framed-compact", "unframed-compact"])
def test_legacy_clients_allowed(proto_factory, trans_factory):
    factory = THeaderProtocolFactory(allowed_client_types=ALL_CLIENT_TYPES)
    with header_server(factory) as port:
        with client_context(
            addressbook.AddressBookService, "127.0.0.1", port,
            proto_factory=proto_factory, trans_factory=trans_factory,
        ) as client:
            exercise(client)


def test_legacy_client_rejected():
    with header_server(THeaderProtocolFactory()) as port:
        with client_context(
            addressbook.AddressBookService, "127.0.0.1", port,
            proto_factory=TBinaryProtocolFactory(),
            trans_factory=TFramedTransportFactory(),
        ) as client:
            with pytest.raises(TTransportException):
                client.add(addressbook.Person(name="x"))


def test_server_requires_header_on_both_sides():
    processor = TProcessor(addressbook.AddressBookService, Dispatcher())
    with pytest.raises(ValueError):
        TServer(processor, TServerSocket(port=0),
                iprot_factory=THeaderProtocolFactory(),
                oprot_factory=TBinaryProtocolFactory())


# wire level tests on memory buffers


class Empty(TPayload):
    thrift_spec = {}
    default_spec = []


def encode_message(proto, seqid=7):
    proto.write_message_begin("ping", TMessageType.CALL, seqid)
    proto.write_struct(Empty())
    proto.write_message_end()
    proto.trans.flush()
    return proto.trans._trans.getvalue()


def header_frame(header, payload, seqid=7):
    header += b"\x00" * ((4 - len(header) % 4) % 4)
    body = struct.pack("!HHiH", HEADER_MAGIC, 0, seqid, len(header) // 4)
    body += header + payload
    return struct.pack("!i", len(body)) + body


def binary_payload():
    # header section is protocol id and transform count, padded to 4 bytes
    return encode_message(THeaderProtocol(TMemoryBuffer()))[18:]


def test_frame_layout():
    proto = THeaderProtocol(TMemoryBuffer())
    proto.set_header(b"k", b"v")
    data = encode_message(proto)

    # protocol id, 0 transforms, KEY_VALUE info, 1 pair, "k", "v"
    assert data == header_frame(b"\x00\x00\x01\x01\x01k\x01v",
                                binary_payload())
    assert struct.unpack("!i", data[:4])[0] == len(data) - 4

    back = THeaderProtocol(TMemoryBuffer(data))
    assert back.read_message_begin() == ("ping", TMessageType.CALL, 7)
    assert back.get_headers() == {b"k": b"v"}
    assert back.trans.sequence_id == 7
    back.read_struct(Empty())
    back.read_message_end()


def test_zlib_transform_roundtrip():
    proto = THeaderProtocol(TMemoryBuffer())
    proto.add_transform(THeaderTransformID.ZLIB)
    data = encode_message(proto)
    assert data[14:17] == b"\x00\x01\x01"  # binary, 1 transform, zlib
    assert zlib.decompress(data[18:]) == binary_payload()

    back = THeaderProtocol(TMemoryBuffer(data))
    assert back.read_message_begin() == ("ping", TMessageType.CALL, 7)


def test_unknown_transform():
    data = header_frame(b"\x00\x01\x7f", b"")
    back = THeaderProtocol(TMemoryBuffer(data))
    with pytest.raises(TApplicationException) as exc:
        back.read_message_begin()
    assert exc.value.type == TApplicationException.INVALID_TRANSFORM

    # the error went back to the peer as a header frame it can read
    reply = THeaderProtocol(TMemoryBuffer(back.trans._trans.getvalue()))
    assert reply.read_message_begin() == ("", TMessageType.EXCEPTION, 7)
    err = TApplicationException()
    reply.read_struct(err)
    assert err.type == TApplicationException.INVALID_TRANSFORM


def test_unknown_protocol_error_uses_previous_protocol():
    # a compact frame asking for protocol id 3 on a compact server
    data = header_frame(b"\x03\x00", b"")
    server = THeaderProtocol(TMemoryBuffer(data),
                             default_protocol=THeaderSubprotocolID.COMPACT)
    with pytest.raises(TApplicationException):
        server.read_message_begin()

    client = THeaderProtocol(TMemoryBuffer(server.trans._trans.getvalue()),
                             default_protocol=THeaderSubprotocolID.COMPACT)
    assert client.read_message_begin() == ("", TMessageType.EXCEPTION, 7)


def test_unknown_info_header_is_skipped():
    data = header_frame(b"\x00\x00\x42\x01\x01k\x01v", binary_payload())
    back = THeaderProtocol(TMemoryBuffer(data))
    assert back.read_message_begin() == ("ping", TMessageType.CALL, 7)
    assert back.get_headers() == {}


@pytest.mark.parametrize("cut", [3, 9])
def test_truncated_payload(cut):
    payload = binary_payload()
    data = header_frame(b"\x00\x00", payload[:cut])
    back = THeaderProtocol(TMemoryBuffer(data))
    # must fail loudly, never decode garbage
    with pytest.raises(Exception):
        back.read_message_begin()
        back.read_struct(Empty())


def test_frame_too_large():
    data = encode_message(THeaderProtocol(TMemoryBuffer()))
    trans = THeaderTransport(TMemoryBuffer(data))
    trans.set_max_frame_size(8)
    with pytest.raises(TTransportException) as exc:
        trans.read_frame()
    assert exc.value.type == TTransportException.SIZE_LIMIT


# interop with the Apache Thrift python library


@pytest.fixture
def apache():
    hp = pytest.importorskip("thrift.protocol.THeaderProtocol")
    from thrift.transport import TTransport
    return hp, TTransport


def apache_encode(apache, sub_protocol, headers=(), transforms=()):
    hp, tt = apache
    buf = tt.TMemoryBuffer()
    proto = hp.THeaderProtocol(buf, (THeaderClientType.HEADERS,),
                               sub_protocol)
    for k, v in headers:
        proto.set_header(k, v)
    for t in transforms:
        proto.add_transform(t)
    proto.writeMessageBegin("ping", TMessageType.CALL, 7)
    proto.writeStructBegin("Empty")
    proto.writeFieldStop()
    proto.writeStructEnd()
    proto.writeMessageEnd()
    proto.trans.flush()
    return buf.getvalue()


@pytest.mark.parametrize("sub_protocol", [THeaderSubprotocolID.BINARY,
                                          THeaderSubprotocolID.COMPACT])
def test_read_apache_frame(apache, sub_protocol):
    data = apache_encode(apache, sub_protocol,
                         headers=[(b"a", b"1"), (b"b", b"2")],
                         transforms=[THeaderTransformID.ZLIB])
    proto = THeaderProtocol(TMemoryBuffer(data))
    assert proto.read_message_begin() == ("ping", TMessageType.CALL, 7)
    assert proto.get_headers() == {b"a": b"1", b"b": b"2"}
    proto.read_struct(Empty())
    proto.read_message_end()
    assert proto.trans.protocol_id == sub_protocol


@pytest.mark.parametrize("sub_protocol", [THeaderSubprotocolID.BINARY,
                                          THeaderSubprotocolID.COMPACT])
def test_apache_reads_our_frame(apache, sub_protocol):
    hp, tt = apache
    proto = THeaderProtocol(TMemoryBuffer(), default_protocol=sub_protocol)
    proto.set_header(b"a", b"1")
    proto.add_transform(THeaderTransformID.ZLIB)
    data = encode_message(proto)

    back = hp.THeaderProtocol(tt.TMemoryBuffer(data),
                              (THeaderClientType.HEADERS,))
    assert back.readMessageBegin() == ("ping", TMessageType.CALL, 7)
    assert back.get_headers() == {b"a": b"1"}
    back.readStructBegin()
    assert back.readFieldBegin()[1] == 0  # stop
    back.readStructEnd()
    back.readMessageEnd()
