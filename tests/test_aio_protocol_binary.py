# -*- coding: utf-8 -*-

from io import BytesIO

import pytest

from thriftpy2.thrift import TType, TPayload
from thriftpy2.contrib.aio.protocol import binary as proto


class TItem(TPayload):
    thrift_spec = {
        1: (TType.I32, "id", False),
        2: (TType.LIST, "phones", (TType.STRING), False),
    }
    default_spec = [("id", None), ("phones", None)]


class AsyncBytesIO:
    def __init__(self, b):
        self.b = b

    async def read(self, *args, **kwargs):
        return self.b.read(*args, **kwargs)


@pytest.mark.asyncio
async def test_strict_decode():
    bs = AsyncBytesIO(BytesIO(b"\x00\x00\x00\x0c\x00"  # there is a redundant '\x00'
                      b"\xe4\xbd\xa0\xe5\xa5\xbd\xe4\xb8\x96\xe7\x95\x8c"))
    with pytest.raises(UnicodeDecodeError):
        await proto.read_val(bs, TType.STRING, decode_response=True,
                             strict_decode=True)
