from __future__ import annotations

from typing import TYPE_CHECKING

from thriftpy2._compat import CYTHON
from thriftpy2.thrift import TApplicationException, TMessageType
from thriftpy2.transport.header import (
    THeaderClientType,
    THeaderSubprotocolID,
    THeaderTransport,
)

from .base import TProtocolBase
from .binary import TBinaryProtocol
from .compact import TCompactProtocol

if TYPE_CHECKING:
    TCyBinaryProtocol = TBinaryProtocol
elif CYTHON:
    from .cybin import TCyBinaryProtocol
else:
    TCyBinaryProtocol = TBinaryProtocol


PROTOCOLS_BY_ID = {
    THeaderSubprotocolID.BINARY: TCyBinaryProtocol,
    THeaderSubprotocolID.COMPACT: TCompactProtocol,
}

# unframed clients are read straight from the wire, the accelerated binary
# protocol needs a Cython transport so the pure Python one is used there
UNFRAMED_PROTOCOLS_BY_ID = {
    **PROTOCOLS_BY_ID,
    THeaderSubprotocolID.BINARY: TBinaryProtocol,
}


class THeaderProtocol(TProtocolBase):
    """Frames binary or compact messages with THeader headers.

    As a client the sub protocol is chosen with ``default_protocol``. As a
    server ``allowed_client_types`` controls whether plain framed or unframed
    binary/compact clients are accepted as well, the reply always uses the
    dialect the client used.
    """

    def __init__(self, trans, allowed_client_types=(
            THeaderClientType.HEADERS,),
            default_protocol=THeaderSubprotocolID.BINARY,
            decode_response=True, strict_decode=False):
        if not isinstance(trans, THeaderTransport):
            trans = THeaderTransport(trans, allowed_client_types,
                                     default_protocol)
        super().__init__(trans)
        self.trans: THeaderTransport = trans
        self.decode_response = decode_response
        self.strict_decode = strict_decode
        # latched by the first read or write, a client always writes its
        # request before reading anything
        self._is_server = None
        self._protocols_key = None
        self._iprot: TProtocolBase
        self._oprot: TProtocolBase
        self._set_protocols()

    def get_headers(self):
        return self.trans.get_headers()

    def set_header(self, key, value):
        self.trans.set_header(key, value)

    def clear_headers(self):
        self.trans.clear_headers()

    def add_transform(self, transform_id):
        self.trans.add_transform(transform_id)

    def _protocol_cls(self, table, protocol_id):
        try:
            return table[protocol_id]
        except KeyError:
            raise TApplicationException(
                TApplicationException.INVALID_PROTOCOL,
                "Unknown protocol requested.")

    def _make_write_protocol(self, protocol_id):
        cls = self._protocol_cls(PROTOCOLS_BY_ID, protocol_id)
        return cls(self.trans.write_buffer,
                   decode_response=self.decode_response,
                   strict_decode=self.strict_decode)

    def _set_protocols(self):
        protocol_id = self.trans.protocol_id
        # a connected peer virtually never changes dialect, rebuild the sub
        # protocols only when it actually does
        key = (self.trans.client_type, protocol_id)
        if key == self._protocols_key:
            return
        kwargs = dict(decode_response=self.decode_response,
                      strict_decode=self.strict_decode)
        if self.trans.is_unframed:
            cls = self._protocol_cls(UNFRAMED_PROTOCOLS_BY_ID, protocol_id)
            self._iprot = cls(self.trans, **kwargs)
        else:
            cls = self._protocol_cls(PROTOCOLS_BY_ID, protocol_id)
            self._iprot = cls(self.trans.read_buffer, **kwargs)
        self._oprot = self._make_write_protocol(protocol_id)
        self._protocols_key = key

    def skip(self, ttype):
        self._iprot.skip(ttype)

    def read_message_begin(self):
        if self._is_server is None:
            self._is_server = True
        prev_protocol_id = self.trans.protocol_id
        try:
            self.trans.read_frame()
            self._set_protocols()
        except TApplicationException as exc:
            if not self._is_server:
                # only a server answers frames it cannot decode, a client
                # must never write an exception into the request stream
                raise
            # reply in the protocol the peer spoke before this frame, the
            # header may have asked for one we cannot provide
            self.trans.reset_protocol_id(prev_protocol_id)
            oprot = self._make_write_protocol(prev_protocol_id)
            oprot.write_message_begin(
                "", TMessageType.EXCEPTION, self.trans.sequence_id)
            oprot.write_struct(exc)
            oprot.write_message_end()
            self.trans.flush()
            raise
        return self._iprot.read_message_begin()

    def read_message_end(self):
        self._iprot.read_message_end()

    def write_message_begin(self, name, ttype, seqid):
        if self._is_server is None:
            self._is_server = False
        self.trans.sequence_id = seqid
        self._oprot.write_message_begin(name, ttype, seqid)

    def write_message_end(self):
        self._oprot.write_message_end()

    def read_struct(self, obj):
        return self._iprot.read_struct(obj)

    def write_struct(self, obj):
        self._oprot.write_struct(obj)


class THeaderProtocolFactory:
    # the sub protocol is detected while reading and replies must use the
    # same dialect, so servers route both directions through one instance
    shared_instance = True

    def __init__(self, allowed_client_types=(THeaderClientType.HEADERS,),
                 default_protocol=THeaderSubprotocolID.BINARY,
                 decode_response=True, strict_decode=False):
        self.allowed_client_types = allowed_client_types
        self.default_protocol = default_protocol
        self.decode_response = decode_response
        self.strict_decode = strict_decode

    def get_protocol(self, trans):
        return THeaderProtocol(trans, self.allowed_client_types,
                               self.default_protocol,
                               self.decode_response, self.strict_decode)
