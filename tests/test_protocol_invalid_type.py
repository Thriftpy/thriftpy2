"""Invalid wire types must fail while a value is being skipped."""

from io import BytesIO

import pytest

from thriftpy2 import _compat
from thriftpy2.contrib.aio.protocol import binary as aio_binary
from thriftpy2.contrib.aio.protocol import compact as aio_compact
from thriftpy2.protocol import binary, compact
from thriftpy2.protocol.exc import TProtocolException
from thriftpy2.thrift import TPayload, TType

if _compat.CYTHON:
    from thriftpy2.protocol import cybin
    from thriftpy2.transport.memory import TCyMemoryBuffer


class LimitedBytesIO(BytesIO):
    """Bound reads so a broken field loop cannot hang the test run."""

    def __init__(self, value=b""):
        super().__init__(value)
        self.reads_left = 20

    def read(self, size=-1):
        self.reads_left -= 1
        if self.reads_left < 0:
            raise AssertionError("protocol did not finish within 20 reads")
        return super().read(size)


class AsyncLimitedBytesIO:
    def __init__(self, value):
        self.buffer = LimitedBytesIO(value)

    async def read(self, size=-1):
        return self.buffer.read(size)


class Known(TPayload):
    thrift_spec = {1: (TType.I32, "number", False)}
    default_spec = [("number", None)]


class WithUnknown(TPayload):
    thrift_spec = {
        1: (TType.I32, "number", False),
        2: (TType.STRING, "extra", False),
    }
    default_spec = [("number", None), ("extra", None)]


class ListValue(TPayload):
    thrift_spec = {1: (TType.LIST, "values", TType.BYTE, False)}
    default_spec = [("values", None)]


class SetValue(TPayload):
    thrift_spec = {1: (TType.SET, "values", TType.BYTE, False)}
    default_spec = [("values", None)]


class MapValue(TPayload):
    thrift_spec = {1: (TType.MAP, "values", (TType.BYTE, TType.BYTE), False)}
    default_spec = [("values", None)]


SYNC_PROTOCOLS = ["binary", "compact"]
if _compat.CYTHON:
    SYNC_PROTOCOLS.append("cybin")
ASYNC_PROTOCOLS = ["aio_binary", "aio_compact"]


def protocol_class(name):
    return {
        "binary": binary.TBinaryProtocol,
        "compact": compact.TCompactProtocol,
        "cybin": cybin.TCyBinaryProtocol if _compat.CYTHON else None,
        "aio_binary": aio_binary.TAsyncBinaryProtocol,
        "aio_compact": aio_compact.TAsyncCompactProtocol,
    }[name]


def buffer_for(name, data=b"", reading=False):
    if name == "cybin":
        # TCyMemoryBuffer enforces exact reads and raises at EOF.
        return TCyMemoryBuffer(data)
    if reading:
        if name.startswith("aio_"):
            return AsyncLimitedBytesIO(data)
        return LimitedBytesIO(data)
    return BytesIO()


def encode(name, obj):
    buffer = buffer_for(name)
    protocol_class(name)(buffer).write_struct(obj)
    return buffer.getvalue()


def corrupt(name, case):
    if case == "field":
        blob = bytearray(encode(name, Known(number=0)))
    elif case in ("list", "set"):
        cls = ListValue if case == "list" else SetValue
        blob = bytearray(encode(name, cls(values=[0])))
    else:
        blob = bytearray(encode(name, MapValue(values={0: 0})))

    if "compact" in name:
        if case == "field":
            index, mask = 0, 0x0f
        elif case in ("list", "set"):
            index, mask = 1, 0x0f
        else:
            index, mask = 2, 0xf0 if case == "map_key" else 0x0f
        # Compact type 0xd is unassigned; preserve the size or field id nibble.
        blob[index] = (blob[index] & ~mask) | (0xd0 if mask == 0xf0 else 0x0d)
    else:
        # Binary type 5 is unassigned. The writer supplies every other byte.
        index = {"field": 0, "list": 3, "set": 3,
                 "map_key": 3, "map_value": 4}[case]
        blob[index] = 5
    return bytes(blob)


def check_invalid(exc, name):
    if name == "cybin":
        assert "Invalid Thrift type" in str(exc.value)
    else:
        assert exc.value.type == TProtocolException.INVALID_DATA


@pytest.mark.parametrize("name", SYNC_PROTOCOLS)
@pytest.mark.parametrize("case", ["field", "list", "set", "map_key", "map_value"])
def test_invalid_type_while_reading_struct(name, case):
    blob = corrupt(name, case)
    expected = cybin.ProtocolError if name == "cybin" else TProtocolException
    with pytest.raises(expected) as exc:
        protocol_class(name)(buffer_for(name, blob, reading=True)).read_struct(Known())
    check_invalid(exc, name)


@pytest.mark.parametrize("name", SYNC_PROTOCOLS)
def test_valid_round_trip_and_unknown_field(name):
    obj = WithUnknown(number=7, extra="ignored")
    blob = encode(name, obj)
    reader = protocol_class(name)(buffer_for(name, blob, reading=True))
    assert read_value(reader, WithUnknown) == obj
    reader = protocol_class(name)(buffer_for(name, blob, reading=True))
    assert read_value(reader, Known) == Known(number=7)


def read_value(reader, cls):
    obj = cls()
    reader.read_struct(obj)
    return obj


@pytest.mark.parametrize("name", SYNC_PROTOCOLS)
def test_skip_rejects_invalid_type(name):
    reader = protocol_class(name)(buffer_for(name, reading=True))
    expected = cybin.ProtocolError if name == "cybin" else TProtocolException
    with pytest.raises(expected) as exc:
        reader.skip(5)
    check_invalid(exc, name)


def test_compact_skip_rejects_stop():
    with pytest.raises(TProtocolException) as exc:
        compact.TCompactProtocol(LimitedBytesIO()).skip(TType.STOP)
    assert exc.value.type == TProtocolException.INVALID_DATA


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ASYNC_PROTOCOLS)
@pytest.mark.parametrize("case", ["field", "list", "set", "map_key", "map_value"])
async def test_async_invalid_type_while_reading_struct(name, case):
    blob = corrupt(name, case)
    reader = protocol_class(name)(buffer_for(name, blob, reading=True))
    with pytest.raises(TProtocolException) as exc:
        await reader.read_struct(Known())
    check_invalid(exc, name)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ASYNC_PROTOCOLS)
async def test_async_valid_round_trip_and_unknown_field(name):
    obj = WithUnknown(number=7, extra="ignored")
    blob = encode(name, obj)
    for cls, expected in [(WithUnknown, obj), (Known, Known(number=7))]:
        reader = protocol_class(name)(buffer_for(name, blob, reading=True))
        result = cls()
        await reader.read_struct(result)
        assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ASYNC_PROTOCOLS)
async def test_async_skip_rejects_invalid_type(name):
    reader = protocol_class(name)(buffer_for(name, reading=True))
    with pytest.raises(TProtocolException) as exc:
        await reader.skip(5)
    check_invalid(exc, name)


@pytest.mark.asyncio
async def test_async_compact_skip_rejects_stop():
    with pytest.raises(TProtocolException) as exc:
        await aio_compact.TAsyncCompactProtocol(AsyncLimitedBytesIO(b"")).skip(TType.STOP)
    assert exc.value.type == TProtocolException.INVALID_DATA
