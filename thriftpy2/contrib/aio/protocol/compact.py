# -*- coding: utf-8 -*-

from __future__ import absolute_import

from struct import unpack

from thriftpy2.protocol.exc import TProtocolException
from thriftpy2.thrift import TException, TType
from thriftpy2.protocol.compact import (
    from_zig_zag,
    CompactType,
    TCompactProtocol,
)

from .base import TAsyncProtocolBase

BIN_TYPES = (TType.STRING, TType.BINARY)


async def read_varint(trans):
    result = 0
    shift = 0

    while True:
        x = await trans.read(1)
        byte = ord(x)
        result |= (byte & 0x7f) << shift
        if byte >> 7 == 0:
            return result
        shift += 7


class TAsyncCompactProtocol(TCompactProtocol,  # Inherit all of the writing
                            TAsyncProtocolBase):
    """Compact implementation of the Thrift protocol driver."""
    PROTOCOL_ID = 0x82
    VERSION = 1
    VERSION_MASK = 0x1f
    TYPE_MASK = 0xe0
    TYPE_BITS = 0x07
    TYPE_SHIFT_AMOUNT = 5

    async def _read_size(self):
        result = await read_varint(self.trans)
        if result < 0:
            raise TException("Length < 0")
        return result

    async def read_message_begin(self):
        proto_id = await self._read_ubyte()
        if proto_id != self.PROTOCOL_ID:
            raise TProtocolException(TProtocolException.BAD_VERSION,
                                     'Bad protocol id in the message: %d'
                                     % proto_id)

        ver_type = await self._read_ubyte()
        type = (ver_type >> self.TYPE_SHIFT_AMOUNT) & self.TYPE_BITS
        version = ver_type & self.VERSION_MASK
        if version != self.VERSION:
            raise TProtocolException(TProtocolException.BAD_VERSION,
                                     'Bad version: %d (expect %d)'
                                     % (version, self.VERSION))
        seqid = await read_varint(self.trans)
        name = await self._read_string()
        return name, type, seqid

    async def read_message_end(self):  # TAsyncClient expects coroutine
        assert len(self._structs) == 0

    async def _read_field_begin(self):
        type = await self._read_ubyte()
        if type & 0x0f == TType.STOP:
            return None, 0, 0

        delta = type >> 4
        if delta == 0:
            fid = from_zig_zag(await read_varint(self.trans))
        else:
            fid = self._last_fid + delta
        self._last_fid = fid

        type = type & 0x0f
        if type == CompactType.TRUE:
            self._bool_value = True
        elif type == CompactType.FALSE:
            self._bool_value = False

        return None, self._get_ttype(type), fid

    def _read_field_end(self):
        pass

    def _read_struct_begin(self):
        self._structs.append(self._last_fid)
        self._last_fid = 0

    def _read_struct_end(self):
        self._last_fid = self._structs.pop()

    async def _read_map_begin(self):
        size = await self._read_size()
        types = 0
        if size > 0:
            types = await self._read_ubyte()
        vtype = self._get_ttype(types)
        ktype = self._get_ttype(types >> 4)
        return ktype, vtype, size

    async def _read_collection_begin(self):
        size_type = await self._read_ubyte()
        size = size_type >> 4
        type = self._get_ttype(size_type)
        if size == 15:
            size = await self._read_size()
        return type, size

    def _read_collection_end(self):
        pass

    async def _read_byte(self):
        result, = unpack('!b', await self.trans.read(1))
        return result

    async def _read_ubyte(self):
        result, = unpack('!B', await self.trans.read(1))
        return result

    async def _read_int(self):
        return from_zig_zag(await read_varint(self.trans))

    async def _read_double(self):
        buff = await self.trans.read(8)
        val, = unpack('<d', buff)
        return val

    async def _read_binary(self):
        length = await self._read_size()
        return await self.trans.read(length)

    async def _read_string(self):
        length = await self._read_size()
        byte_payload = await self.trans.read(length)

        if self.decode_response:
            try:
                byte_payload = byte_payload.decode('utf-8')
            except UnicodeDecodeError:
                pass
        return byte_payload

    async def _read_bool(self):
        if self._bool_value is not None:
            result = self._bool_value
            self._bool_value = None
            return result
        return (await self._read_byte()) == CompactType.TRUE

    async def read_struct(self, obj):
        self._read_struct_begin()
        while True:
            fname, ftype, fid = await self._read_field_begin()
            if ftype == TType.STOP:
                break

            if fid not in obj.thrift_spec:
                await self.skip(ftype)
                continue

            try:
                field = obj.thrift_spec[fid]
            except IndexError:
                await self.skip(ftype)
                raise
            else:
                if field is not None and \
                        (ftype == field[0]
                         or (ftype in BIN_TYPES
                             and field[0] in BIN_TYPES)):
                    fname = field[1]
                    fspec = field[2]
                    val = await self._read_val(field[0], fspec)
                    setattr(obj, fname, val)
                else:
                    await self.skip(ftype)
            self._read_field_end()
        self._read_struct_end()

    async def _read_val(self, ttype, spec=None):
        if ttype == TType.BOOL:
            return await self._read_bool()

        elif ttype == TType.BYTE:
            return await self._read_byte()

        elif ttype in (TType.I16, TType.I32, TType.I64):
            return await self._read_int()

        elif ttype == TType.DOUBLE:
            return await self._read_double()

        elif ttype == TType.BINARY:
            return await self._read_binary()

        elif ttype == TType.STRING:
            return await self._read_string()

        elif ttype in (TType.LIST, TType.SET):
            if isinstance(spec, tuple):
                v_type, v_spec = spec[0], spec[1]
            else:
                v_type, v_spec = spec, None
            result = []
            r_type, sz = await self._read_collection_begin()

            for i in range(sz):
                result.append(await self._read_val(v_type, v_spec))

            self._read_collection_end()
            return result

        elif ttype == TType.MAP:
            if isinstance(spec[0], int):
                k_type = spec[0]
                k_spec = None
            else:
                k_type, k_spec = spec[0]

            if isinstance(spec[1], int):
                v_type = spec[1]
                v_spec = None
            else:
                v_type, v_spec = spec[1]

            result = {}
            sk_type, sv_type, sz = await self._read_map_begin()
            if sk_type != k_type or sv_type != v_type:
                for _ in range(sz):
                    await self.skip(sk_type)
                    await self.skip(sv_type)
                self._read_collection_end()
                return {}

            for i in range(sz):
                k_val = await self._read_val(k_type, k_spec)
                v_val = await self._read_val(v_type, v_spec)
                result[k_val] = v_val
            self._read_collection_end()
            return result

        elif ttype == TType.STRUCT:
            obj = spec()
            await self.read_struct(obj)
            return obj

    async def skip(self, ttype):
        if ttype == TType.STOP:
            return

        elif ttype == TType.BOOL:
            await self._read_bool()

        elif ttype == TType.BYTE:
            await self._read_byte()

        elif ttype in (TType.I16, TType.I32, TType.I64):
            from_zig_zag(await read_varint(self.trans))

        elif ttype == TType.DOUBLE:
            await self._read_double()

        elif ttype == TType.BINARY:
            await self._read_binary()

        elif ttype == TType.STRING:
            await self._read_string()

        elif ttype == TType.STRUCT:
            self._read_struct_begin()
            while True:
                name, ttype, id = await self._read_field_begin()
                if ttype == TType.STOP:
                    break
                await self.skip(ttype)
                self._read_field_end()
            self._read_struct_end()

        elif ttype == TType.MAP:
            ktype, vtype, size = await self._read_map_begin()
            for i in range(size):
                await self.skip(ktype)
                await self.skip(vtype)
            self._read_collection_end()

        elif ttype == TType.SET:
            etype, size = await self._read_collection_begin()
            for i in range(size):
                await self.skip(etype)
            self._read_collection_end()

        elif ttype == TType.LIST:
            etype, size = await self._read_collection_begin()
            for i in range(size):
                await self.skip(etype)
            self._read_collection_end()


class TAsyncCompactProtocolFactory(object):
    def __init__(self, decode_response=True):
        self.decode_response = decode_response

    def get_protocol(self, trans):
        return TAsyncCompactProtocol(
            trans,
            decode_response=self.decode_response,
        )
