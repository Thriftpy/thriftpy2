"""
Transport for json protocol that apache thrift files will understand
unfortunately, thriftpy2's TJSONProtocol is not compatible with apache's
"""

import json
import base64
from typing import Any

import ijson

from thriftpy2.protocol import TProtocolBase
from thriftpy2.thrift import TType


CTYPES = {
    TType.BOOL: 'tf',
    TType.BYTE: 'i8',
    TType.I16: 'i16',
    TType.I32: 'i32',
    TType.I64: 'i64',
    TType.DOUBLE: 'dbl',
    TType.STRING: 'str',
    TType.BINARY: 'str',  # apache sends binary data as base64 encoded
    TType.STRUCT: 'rec',
    TType.LIST: 'lst',
    TType.SET: 'set',
    TType.MAP: 'map',
}

JTYPES = {v: k for k, v in CTYPES.items()}

VERSION = 1


def _spec_ttype(spec):
    """
    Return the TType of a thrift spec entry.

    A spec entry is one of: a bare TType int, a struct class, or a tuple
    ``(ttype, sub_spec)`` describing a container or a struct.
    """
    if isinstance(spec, tuple):
        return spec[0]
    if hasattr(spec, 'thrift_spec'):
        return TType.STRUCT
    return spec


def _ensure_b64_encode(val):
    """
    Ensure that the variable is something that we can encode with b64encode
    python3 needs bytes, python2 needs string
    """
    if isinstance(val, str):
        return val.encode()
    return val


class _ListSink:
    """Minimal coroutine-like sink for ijson's items_coro pipeline.

    ijson's chained-coroutine API calls ``target.send(item)`` on its sink, so
    a plain ``list.append`` won't work as a target. This wrapper exposes a
    ``send`` (and ``close``) so a list can act as the sink directly.
    """
    __slots__ = ('_target',)

    def __init__(self, target):
        self._target = target

    def send(self, item):
        self._target.append(item)

    def close(self):
        pass


class TApacheJSONProtocolFactory:
    def get_protocol(self, trans):
        return TApacheJSONProtocol(trans)


class TApacheJSONProtocol(TProtocolBase):
    """
    Protocol that implements the Apache JSON Protocol
    """

    def __init__(self, trans):
        TProtocolBase.__init__(self, trans)
        self._req: Any = None

    def _load_data(self):
        # Fast path: transports that buffer the whole message expose getvalue()
        getvalue = getattr(self.trans, 'getvalue', None)
        if getvalue is not None:
            try:
                data = getvalue()
                self._req = json.loads(data.decode('utf8')) if data else None
                return
            except Exception:
                pass

        # Streaming path: feed bytes to ijson's push parser; stop the moment
        # the top-level value is fully materialized. trans.read(n) blocks until
        # exactly n bytes arrive and Apache JSON has no length prefix, so we
        # must read one byte at a time to avoid consuming past the message end.
        items = []
        sink = _ListSink(items)
        coro = ijson.items_coro(sink, '')
        try:
            while not items:
                chunk = self.trans.read(1)
                if not chunk:
                    break
                coro.send(chunk)
        finally:
            try:
                coro.close()
            except Exception:
                pass

        self._req = items[0] if items else None

    def read_message_begin(self):
        self._load_data()
        return self._req[1:4]

    def read_message_end(self):
        self._req = None

    def skip(self, ttype):
        pass

    def write_message_end(self):
        pass

    def write_message_begin(self, name, ttype, seqid):
        self.api = name
        self.ttype = ttype
        self.seqid = seqid

    def write_struct(self, obj):
        """
        Write json to self.trans following apache style jsonification of `obj`

        :param obj: A thriftpy2 object
        :return:
        """
        doc = [VERSION, self.api, self.ttype, self.seqid, self._thrift_to_dict(obj)]
        json_str = json.dumps(doc, separators=(',', ':'))
        self.trans.write(json_str.encode("utf8"))

    def _thrift_to_dict(self, thrift_obj: Any, item_type: Any = None) -> Any:
        """
        Convert a thriftpy2 into an apache conformant dict, eg:

        >>> {0: {'rec': {1: {'str': "304"}, 14: {'rec': {1: {'lst': ["rec", 0]}}}}}}

        >>> {"0":{"rec":{"1":{"str":"284"},"14":{"rec":{"1":{"lst":
        >>>  ["rec",2,{"1":{"i32":12345.0},"2":{"i32":2.0},"3":{"str":"Testing notifications"},"4":{"tf":1}},
              {"1":{"i32":567809.0},"2":{"i32":2.0},"3":{"str":"Other test"},"4":{"tf":0}}]}}}}}}

        :param thrift_obj: the thing we want to make into a dict
        :param item_type: spec describing the type of ``thrift_obj``, in the
            same shape as the element specs found in ``thrift_spec``
        :return:
        """
        if hasattr(thrift_obj, 'thrift_spec'):
            result = {}
            for field_idx, thrift_spec in thrift_obj.thrift_spec.items():
                ttype, field_name, raw_spec = thrift_spec[:3]
                val = getattr(thrift_obj, field_name)
                if val is None:
                    continue
                if ttype in (TType.LIST, TType.SET, TType.MAP, TType.STRUCT):
                    spec: Any = (ttype, raw_spec)
                else:
                    spec = ttype
                result[field_idx] = {CTYPES[ttype]: self._thrift_to_dict(val, spec)}
            return result

        if item_type is None:
            if isinstance(thrift_obj, bool):
                return int(thrift_obj)
            return thrift_obj

        ttype = _spec_ttype(item_type)
        sub_spec: Any = item_type[1] if isinstance(item_type, tuple) and len(item_type) > 1 else None
        if ttype in (TType.LIST, TType.SET):
            # format is [item_type, length, items...]
            return [CTYPES[_spec_ttype(sub_spec)], len(thrift_obj)] + [
                self._thrift_to_dict(v, sub_spec) for v in thrift_obj
            ]
        if ttype == TType.MAP:
            key_spec, val_spec = sub_spec
            # format is [key_type, value_type, length, dict]
            return [CTYPES[_spec_ttype(key_spec)], CTYPES[_spec_ttype(val_spec)], len(thrift_obj), {
                self._thrift_to_dict(k, key_spec): self._thrift_to_dict(v, val_spec)
                for k, v in thrift_obj.items()
            }]
        if ttype == TType.BINARY and TType.BINARY != TType.STRING:
            return base64.b64encode(_ensure_b64_encode(thrift_obj)).decode('ascii')
        if ttype == TType.BOOL:
            return int(thrift_obj)
        return thrift_obj

    def _dict_to_thrift(self, data: Any, base_type: Any) -> Any:
        """
        Convert an apache thrift dict (where key is the type, value is the data)

        :param data: the dict data
        :param base_type: the type we are going to convert data to
        :return:
        """
        # if the result is a python type, return it:
        if data is None:
            return None
        if isinstance(data, (str, int, float, bool)):
            if base_type in (TType.I08, TType.I16, TType.I32, TType.I64):
                return int(data)
            if base_type == TType.BINARY and TType.BINARY != TType.STRING:
                assert isinstance(data, str)
                return base64.b64decode(data)
            if base_type == TType.BOOL:
                return {
                    'true': True,
                    'false': False,
                    '1': True,
                    '0': False
                }[str(data).lower()]
            if isinstance(data, bool):
                return int(data)
            return data

        if isinstance(base_type, tuple):
            assert len(base_type) >= 2
            container_type = base_type[0]
            item_type = base_type[1]
            if container_type == TType.STRUCT:
                return self._dict_to_thrift(data, item_type)
            elif container_type in (TType.LIST, TType.SET):
                return [self._dict_to_thrift(v, item_type) for v in data[2:]]
            elif container_type == TType.MAP:
                assert isinstance(item_type, tuple) and len(item_type) >= 2
                return {
                    self._dict_to_thrift(k, item_type[0]):
                        self._dict_to_thrift(v, item_type[1]) for k, v in data[3].items()
                }
            raise ValueError(f"Unsupported container type: {container_type}")
        result = {}
        base_spec = base_type.thrift_spec
        for field_idx, val in data.items():
            thrift_spec = base_spec[int(field_idx)]
            # spec has field type, field name, (sub spec), False
            field_name = thrift_spec[1]
            for ftype, value in val.items():
                ttype = JTYPES[ftype]
                if thrift_spec[0] == TType.BINARY and TType.BINARY != TType.STRING:
                    bin_data = val.get('str', '')
                    m = len(bin_data) % 4
                    if m != 0:
                        bin_data += '=' * (4-m)
                    result[field_name] = base64.b64decode(bin_data)

                elif ttype == TType.STRUCT:
                    result[field_name] = self._dict_to_thrift(value, thrift_spec[2])
                elif ttype in (TType.LIST, TType.SET):
                    result[field_name] = [self._dict_to_thrift(v, thrift_spec[2]) for v in value[2:]]
                elif ttype == TType.MAP:
                    key_spec = thrift_spec[2][0]
                    val_spec = thrift_spec[2][1]
                    result[field_name] = {
                        self._dict_to_thrift(k, key_spec): self._dict_to_thrift(v, val_spec)
                        for k, v in value[3].items()
                    }
                else:
                    result[field_name] = {
                        'tf': bool,
                        'i8': int,
                        'i16': int,
                        'i32': int,
                        'i64': int,
                        'dbl': float,
                        'str': str,
                    }[ftype](value)
        if callable(base_type):
            return base_type(**result)
        else:
            for k, v in result.items():
                setattr(base_type, k, v)
            return base_type

    def read_struct(self, obj):
        """
        Read the next struct into obj, usually the argument from an incoming request
        Only really used to read the arguments off a request into whatever we want
        see thriftpy2.thrift.TProcessor.process_in for how this class will be used

        Will turn the contents of self.req[4] into the args of obj,
        ie. self.req[4]["1"] must be rendered into obj.thrift_spec

        :param obj:
        :return:
        """
        return self._dict_to_thrift(self._req[4], obj)
