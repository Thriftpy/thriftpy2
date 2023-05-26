# -*- coding: utf-8 -*-

from thriftpy2.protocol import TProtocolBase


class TAsyncProtocolBase(TProtocolBase):
    """Base class for Thrift async protocol layer."""

    async def skip(self, ttype):
        raise NotImplementedError

    async def read_message_begin(self):
        raise NotImplementedError

    async def read_message_end(self):
        raise NotImplementedError

    def write_message_begin(self, name, ttype, seqid):
        raise NotImplementedError

    def write_message_end(self):
        raise NotImplementedError

    async def read_struct(self, obj):
        raise NotImplementedError

    def write_struct(self, obj):
        raise NotImplementedError
