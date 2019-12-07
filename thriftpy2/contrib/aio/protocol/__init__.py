__all__ = [
    'TAsyncProtocolBase',
    'TAsyncBinaryProtocol',
    'TAsyncBinaryProtocolFactory',
    'TAsyncCompactProtocol',
    'TAsyncCompactProtocolFactory',
]

import asyncio


class TAsyncProtocolBase(object):  # TODO: TProtocolBase?
    """Base class for Thrift async protocol layer."""

    def __init__(self, trans):
        self.trans = trans

    @asyncio.coroutine
    def skip(self, ttype):
        raise NotImplementedError

    @asyncio.coroutine
    def read_message_begin(self):
        raise NotImplementedError

    @asyncio.coroutine
    def read_message_end(self):
        raise NotImplementedError

    def write_message_begin(self, name, ttype, seqid):
        raise NotImplementedError

    def write_message_end(self):
        raise NotImplementedError

    @asyncio.coroutine
    def read_struct(self, obj):
        raise NotImplementedError

    def write_struct(self, obj):
        raise NotImplementedError


from .binary import (
    TAsyncBinaryProtocol,  # noqa
    TAsyncBinaryProtocolFactory,  # noqa
)
from .compact import (
    TAsyncCompactProtocol,  # noqa
    TAsyncCompactProtocolFactory,  # noqa
)
