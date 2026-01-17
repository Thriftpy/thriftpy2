# -*- coding: utf-8 -*-

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol


class TProtocolFactory(Protocol):
    """Protocol factory interface for type annotations."""

    def get_protocol(self, trans):
        """Return a protocol instance for the given transport."""
        ...


class TProtocolBase(object):
    """Base class for Thrift protocol layer."""

    def __init__(self, trans):
        self.trans = trans  # transport is public and used by TClient

    def skip(self, ttype):
        raise NotImplementedError

    def read_message_begin(self):
        raise NotImplementedError

    def read_message_end(self):
        raise NotImplementedError

    def write_message_begin(self, name, ttype, seqid):
        raise NotImplementedError

    def write_message_end(self):
        raise NotImplementedError

    def read_struct(self, obj):
        raise NotImplementedError

    def write_struct(self, obj):
        raise NotImplementedError
