import contextlib
import struct
import threading
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

from _helpers import bound_port, wait_for_port

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


@contextlib.contextmanager
def header_server(proto_factory):
    server = make_server(
        addressbook.AddressBookService,
        Dispatcher(),
        host="127.0.0.1",
        port=0,
        proto_factory=proto_factory,
        trans_factory=TBufferedTransportFactory(),
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    port = bound_port(lambda: server.trans.sock)
    wait_for_port(port)
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


def test_wrapped_header_factory_shares_instance():
    # a wrapper factory must forward the shared instance declaration so
    # the server guard cannot be bypassed
    from thriftpy2.protocol import TMultiplexedProtocolFactory
    factory = TMultiplexedProtocolFactory(THeaderProtocolFactory(), "svc")
    assert factory.shared_instance

    processor = TProcessor(addressbook.AddressBookService, Dispatcher())
    with pytest.raises(ValueError):
        TServer(processor, TServerSocket(port=0),
                iprot_factory=factory,
                oprot_factory=TBinaryProtocolFactory())


@pytest.mark.parametrize("proto_factory,trans_factory", [
    (THeaderProtocolFactory(allowed_client_types=ALL_CLIENT_TYPES),
     TBufferedTransportFactory()),
    (TBinaryProtocolFactory(), TBufferedTransportFactory()),
    (TCompactProtocolFactory(), TFramedTransportFactory()),
], ids=["header", "unframed-binary", "framed-compact"])
def test_header_over_http(proto_factory, trans_factory):
    from thriftpy2 import http

    server = http.make_server(
        addressbook.AddressBookService, Dispatcher(),
        host="127.0.0.1", port=0,
        proto_factory=THeaderProtocolFactory(
            allowed_client_types=ALL_CLIENT_TYPES))
    # HTTPServer binds in its constructor, so the port is known already
    port = server.httpd.server_address[1]
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    try:
        with http.client_context(
            addressbook.AddressBookService, "127.0.0.1", port,
            proto_factory=proto_factory, trans_factory=trans_factory,
        ) as client:
            exercise(client)
    finally:
        server.httpd.shutdown()
        thread.join(timeout=1)


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
    # must fail with a clean transport error, never decode garbage
    with pytest.raises(TTransportException) as exc:
        back.read_message_begin()
        back.read_struct(Empty())
    assert exc.value.type == TTransportException.END_OF_FILE


def test_client_does_not_answer_undecodable_reply():
    written = []

    class RecordingBuffer(TMemoryBuffer):
        def write(self, buf):
            written.append(bytes(buf))
            super().write(buf)

    trans = RecordingBuffer()
    proto = THeaderProtocol(trans)
    encode_message(proto)  # the request write latches the client role
    written.clear()

    # a reply with an unknown transform
    trans.setvalue(header_frame(b"\x00\x01\x7f", b""))
    with pytest.raises(TApplicationException):
        proto.read_message_begin()
    # a client must never write an exception frame back towards the server
    assert written == []

    # a reply asking for an unknown protocol must not corrupt the
    # negotiated protocol id of later requests
    trans.setvalue(header_frame(b"\x03\x00", b""))
    with pytest.raises(TApplicationException):
        proto.read_message_begin()
    assert written == []
    assert proto.trans.protocol_id == THeaderSubprotocolID.BINARY


def test_failed_read_does_not_poison_next_message():
    # compact keeps parse state on the protocol instance, a failed read
    # must not leak it into the next message via the protocol cache
    proto = THeaderProtocol(TMemoryBuffer(),
                            default_protocol=THeaderSubprotocolID.COMPACT)
    payload = encode_message(proto)[18:]
    truncated = header_frame(b"\x02\x00", payload[:-1])
    good = header_frame(b"\x02\x00", payload)

    back = THeaderProtocol(TMemoryBuffer(truncated + good),
                           default_protocol=THeaderSubprotocolID.COMPACT)
    assert back.read_message_begin() == ("ping", TMessageType.CALL, 7)
    with pytest.raises(TTransportException):
        back.read_struct(Empty())

    assert back.read_message_begin() == ("ping", TMessageType.CALL, 7)
    back.read_struct(Empty())
    back.read_message_end()


def test_oversized_headers_rejected():
    proto = THeaderProtocol(TMemoryBuffer())
    proto.set_header(b"k", b"x" * 300000)
    with pytest.raises(TTransportException) as exc:
        encode_message(proto)
    assert exc.value.type == TTransportException.SIZE_LIMIT


def test_plain_protocol_over_header_transport():
    # a plain protocol layered over THeaderTransport via the transport
    # factory, both for a detected unframed client and a framed one
    from thriftpy2.protocol.binary import TBinaryProtocol
    from thriftpy2.transport.header import THeaderTransportFactory

    factory = THeaderTransportFactory(allowed_client_types=ALL_CLIENT_TYPES)
    payload = binary_payload()
    framed = struct.pack("!i", len(payload)) + payload
    for data in (payload, framed):
        trans = factory.get_transport(TMemoryBuffer(data))
        proto = TBinaryProtocol(trans)
        assert proto.read_message_begin() == ("ping", TMessageType.CALL, 7)
        proto.read_struct(Empty())
        proto.read_message_end()


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
