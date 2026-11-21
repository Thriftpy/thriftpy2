from io import BytesIO

import pytest

from thriftpy2.thrift import TType, TPayload
from thriftpy2.contrib.aio.protocol import compact
from thriftpy2.protocol.exc import TProtocolException
from test_aio_protocol_binary import AsyncBytesIO, TIntKeyMap, TStringKeyMap
from test_protocol_compact import INVALID_TYPE_CASES


class TItem(TPayload):
    thrift_spec = {
        1: (TType.I32, "id", False),
        2: (TType.LIST, "phones", (TType.STRING), False),
    }
    default_spec = [("id", None), ("phones", None)]


def gen_proto(bytearray=b''):
    b = AsyncBytesIO(BytesIO(bytearray))
    proto = compact.TAsyncCompactProtocol(b)
    return (b, proto)


@pytest.mark.asyncio
async def test_strict_decode():
    b, proto = gen_proto(b'\x0c\xe4\xbd\xa0\xe5\xa5\x00'
                         b'\xbd\xe4\xb8\x96\xe7\x95\x8c')
    proto.strict_decode = True

    with pytest.raises(UnicodeDecodeError):
        await proto._read_val(TType.STRING)


@pytest.mark.asyncio
async def test_read_struct_skips_map_with_mismatched_key_type():
    b = BytesIO()
    compact.TAsyncCompactProtocol(b).write_struct(
        TStringKeyMap(m={"abcd": 1, "efgh": 2}, x=5))
    _, proto = gen_proto(b.getvalue())
    obj = TIntKeyMap()
    await proto.read_struct(obj)
    assert obj == TIntKeyMap(m={}, x=5)


@pytest.mark.asyncio
async def test_read_struct_skips_list_with_mismatched_element_type():
    class TIntList(TPayload):
        thrift_spec = {
            1: (TType.LIST, "l", TType.I32, False),
            2: (TType.I32, "x", False),
        }
        default_spec = [("l", None), ("x", None)]

    class TStringList(TPayload):
        thrift_spec = {
            1: (TType.LIST, "l", TType.STRING, False),
            2: (TType.I32, "x", False),
        }
        default_spec = [("l", None), ("x", None)]

    b = BytesIO()
    compact.TAsyncCompactProtocol(b).write_struct(
        TStringList(l=["ab", "cd"], x=99))
    _, proto = gen_proto(b.getvalue())
    obj = TIntList()
    await proto.read_struct(obj)
    assert obj == TIntList(l=[], x=99)


@pytest.mark.parametrize("data", list(INVALID_TYPE_CASES.values()),
                         ids=list(INVALID_TYPE_CASES))
@pytest.mark.asyncio
async def test_read_struct_rejects_invalid_type(data):
    _, proto = gen_proto(data)
    with pytest.raises(TProtocolException) as exc:
        await proto.read_struct(TItem())
    assert exc.value.type == TProtocolException.INVALID_DATA


@pytest.mark.parametrize("ttype", [TType.STOP, 5])
@pytest.mark.asyncio
async def test_skip_rejects_invalid_type(ttype):
    _, proto = gen_proto()
    with pytest.raises(TProtocolException) as exc:
        await proto.skip(ttype)
    assert exc.value.type == TProtocolException.INVALID_DATA
