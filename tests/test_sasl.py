import struct

import pytest

import thriftpy2.transport.sasl as sasl_module
from thriftpy2._compat import CYTHON
from thriftpy2.transport import TTransportException

START = 1
OK = 2
BAD = 3
ERROR = 4
COMPLETE = 5


class FakeSaslClient(object):
    """Mimics the interface of sasl.Client.

    With wrap=False it behaves like a QOP=auth negotiation where
    encode/decode pass data through unchanged. With wrap=True it
    emulates auth-int/auth-conf by adding a length header and a one
    byte marker around the payload.
    """

    def __init__(self, mechanism=b'PLAIN', initial=b'initial', wrap=False):
        self.mechanism = mechanism
        self.initial = initial
        self.wrap = wrap
        self.challenges = []

    def start(self, mechanism):
        return True, self.mechanism, self.initial

    def step(self, challenge):
        self.challenges.append(challenge)
        return True, b'response'

    def encode(self, data):
        if self.wrap:
            wrapped = b'X' + data
            return True, struct.pack('>I', len(wrapped)) + wrapped
        return True, data

    def decode(self, data):
        # data contains the 4 byte length header plus the wrapped payload
        return True, data[5:]

    def getError(self):
        return 'fake sasl error'


class LoopbackTransport(object):
    """In-memory transport with scripted input and recorded output."""

    def __init__(self, inbuf=b''):
        self.inbuf = inbuf
        self.out = []
        self.opened = True

    def is_open(self):
        return self.opened

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    def read(self, sz):
        ret, self.inbuf = self.inbuf[:sz], self.inbuf[sz:]
        return ret

    def write(self, data):
        self.out.append(data)

    def flush(self):
        pass


def sasl_message(status, payload):
    return struct.pack('>BI', status, len(payload)) + payload


def data_frame(payload):
    return struct.pack('>I', len(payload)) + payload


transport_classes = [sasl_module.TSaslClientTransport]
if CYTHON:
    transport_classes.append(sasl_module.TCySaslClientTransport)


@pytest.fixture(params=transport_classes,
                ids=[cls.__name__ for cls in transport_classes])
def transport_cls(request):
    return request.param


def make_transport(transport_cls, sasl=None, inbuf=b''):
    sasl = sasl or FakeSaslClient()
    trans = LoopbackTransport(inbuf)
    return transport_cls(lambda: sasl, 'PLAIN', trans), sasl, trans


def open_transport(transport_cls, sasl=None, inbuf=b''):
    t, sasl, trans = make_transport(
        transport_cls, sasl, sasl_message(COMPLETE, b'') + inbuf)
    t.open()
    trans.out = []
    return t, sasl, trans


def test_negotiation(transport_cls):
    server_replies = sasl_message(OK, b'challenge') + sasl_message(COMPLETE, b'')
    t, sasl, trans = make_transport(transport_cls, inbuf=server_replies)
    t.open()

    assert trans.out == [
        sasl_message(START, b'PLAIN'),
        sasl_message(OK, b'initial'),
        sasl_message(OK, b'response'),
    ]
    assert sasl.challenges == [b'challenge']


def test_negotiation_with_str_mechanism_and_none_initial(transport_cls):
    sasl = FakeSaslClient(mechanism='PLAIN', initial=None)
    t, sasl, trans = make_transport(
        transport_cls, sasl, sasl_message(COMPLETE, b''))
    t.open()

    assert trans.out == [
        sasl_message(START, b'PLAIN'),
        sasl_message(OK, b''),
    ]


def test_negotiation_bad_status(transport_cls):
    t, _, _ = make_transport(
        transport_cls, inbuf=sasl_message(BAD, b'denied'))
    with pytest.raises(TTransportException, match='Bad status'):
        t.open()


def test_open_twice(transport_cls):
    t, _, _ = open_transport(transport_cls)
    with pytest.raises(TTransportException, match='Already open') as exc:
        t.open()
    assert exc.value.type == TTransportException.ALREADY_OPEN


def test_write_flush_plain(transport_cls):
    t, _, trans = open_transport(transport_cls)
    t.write(b'hello')
    t.flush()
    assert trans.out == [data_frame(b'hello')]


def test_read_within_frame(transport_cls):
    t, _, trans = open_transport(transport_cls)
    t.write(b'x')
    t.flush()  # decide QOP before reading

    trans.inbuf = data_frame(b'\x00\x07abcd')
    assert t.read(2) == b'\x00\x07'
    assert t.read(4) == b'abcd'


def test_read_across_frames(transport_cls):
    t, _, trans = open_transport(transport_cls)
    t.write(b'x')
    t.flush()

    # one i32 split across two frames, then more data in the second frame
    trans.inbuf = data_frame(b'\x00\x00') + data_frame(b'\x00\x07abcd')
    assert t.read(4) == b'\x00\x00\x00\x07'
    assert t.read(4) == b'abcd'


def test_read_eof(transport_cls):
    t, _, trans = open_transport(transport_cls)
    t.write(b'x')
    t.flush()

    trans.inbuf = data_frame(b'ab')
    with pytest.raises(TTransportException) as exc:
        t.read(4)
    assert exc.value.type == TTransportException.END_OF_FILE


def test_wrapped_roundtrip(transport_cls):
    sasl = FakeSaslClient(wrap=True)
    t, sasl, trans = open_transport(transport_cls, sasl)

    t.write(b'hello')
    t.flush()  # encode changes the length, so QOP wrapping is detected
    assert trans.out == [data_frame(b'Xhello')]

    trans.inbuf = data_frame(b'Xworld')
    assert t.read(5) == b'world'


def test_close_and_reopen(transport_cls):
    t, _, trans = open_transport(transport_cls)
    t.close()
    assert not trans.is_open()

    trans.inbuf = sasl_message(COMPLETE, b'')
    t.open()
    t.write(b'hello')
    t.flush()
    assert trans.out[-1] == data_frame(b'hello')
