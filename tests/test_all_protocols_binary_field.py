from __future__ import absolute_import

import time
import traceback
from multiprocessing import Process

import pytest
import six

from thriftpy2.thrift import TType, TPayloadMeta
try:
    from thriftpy2.protocol import cybin
except ImportError:
    cybin = None
import thriftpy2
from thriftpy2.http import (
    make_server as make_http_server,
    make_client as make_http_client,
)
from thriftpy2.protocol import (
    TApacheJSONProtocolFactory,
    TJSONProtocolFactory,
    TCompactProtocolFactory,
)
from thriftpy2.protocol import TBinaryProtocolFactory
from thriftpy2.rpc import make_server as make_rpc_server, \
    make_client as make_rpc_client
from thriftpy2.transport import TBufferedTransportFactory, TCyMemoryBuffer

protocols = [TApacheJSONProtocolFactory,
             TJSONProtocolFactory,
             TBinaryProtocolFactory,
             TCompactProtocolFactory]


def recursive_vars(obj):
    if isinstance(obj, six.string_types):
        return six.ensure_str(obj)
    if isinstance(obj, six.binary_type):
        return six.ensure_binary(obj)
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: recursive_vars(v) for k, v in obj.items()}
    if isinstance(obj, (list, set)):
        return [recursive_vars(v) for v in obj]
    if hasattr(obj, '__dict__'):
        return recursive_vars(vars(obj))


@pytest.mark.parametrize('server_func',
                         [(make_rpc_server, make_rpc_client),
                          (make_http_server, make_http_client)])
@pytest.mark.parametrize('tlist', [[], ['a', 'b', 'c']])
@pytest.mark.parametrize('binary', [b'', b'\x01\x03test binary\x03\xff'])
@pytest.mark.parametrize('proto_factory', protocols)
def test_protocols(proto_factory, binary, tlist, server_func):
    test_thrift = thriftpy2.load(
        "apache_json_test.thrift",
        module_name="test_thrift"
    )
    Foo = test_thrift.Foo

    class Handler(object):
        @staticmethod
        def test(t):
            return t

    trans_factory = TBufferedTransportFactory

    def run_server():
        server = server_func[0](
            test_thrift.TestService,
            handler=Handler(),
            host='localhost',
            port=9090,
            proto_factory=proto_factory(),
            trans_factory=trans_factory(),
        )
        server.serve()

    proc = Process(target=run_server)
    proc.start()
    time.sleep(0.2)
    err = None
    try:
        test_object = test_thrift.Test(
            tdouble=12.3456,
            tint=567,
            tstr='A test \'{["string',
            tbinary=binary,
            tlist_of_strings=tlist,
            tbool=False,
            tbyte=16,
            tlong=123123123,
            tshort=123,
            tsetofints={1, 2, 3, 4, 5},
            tmap_of_int2str={
                1: "one",
                2: "two",
                3: "three"
            },
            tmap_of_str2foo={'first': Foo("first"), "2nd": Foo("baz")},
            tmap_of_str2foolist={
                'test': [Foo("test list entry")]
            },
            tmap_of_str2mapofstring2foo={
                "first": {
                    "second": Foo("testing")
                }
            },
            tmap_of_str2stringlist={
                "words": ["dog", "cat", "pie"],
                "other": ["test", "foo", "bar", "baz", "quux"]
            },
            tfoo=Foo("test food"),
            tlist_of_foo=[Foo("1"), Foo("2"), Foo("3")],
            tlist_of_maps2int=[
                {"one": 1, "two": 2, "three": 3}
            ],
            tmap_of_int2foo={
                1: Foo("One"),
                2: Foo("Two"),
                5: Foo("Five")
            },
            tbin2bin={b'Binary': b'data'},
            tset_of_binary={b'bin one', b'bin two'},
            tlist_of_binary=[b'foo roo', b'baz boo'],
        )

        client = server_func[1](
            test_thrift.TestService,
            host='localhost',
            port=9090,
            proto_factory=proto_factory(),
            trans_factory=trans_factory(),
        )
        res = client.test(test_object)
        assert recursive_vars(res) == recursive_vars(test_object)
    except Exception as e:
        traceback.print_exc()
        err = e
    finally:
        proc.terminate()
    if err:
        raise err
    time.sleep(0.1)


@pytest.mark.parametrize('server_func',
                         [(make_rpc_server, make_rpc_client),
                          (make_http_server, make_http_client)])
@pytest.mark.parametrize('proto_factory', protocols)
def test_exceptions(server_func, proto_factory):
    test_thrift = thriftpy2.load(
        "apache_json_test.thrift",
        module_name="test_thrift"
    )
    TestException = test_thrift.TestException

    class Handler(object):
        def do_error(self, arg):
            raise TestException(message=arg)

    def do_server():
        server = server_func[0](
            service=test_thrift.TestService,
            handler=Handler(),
            host='localhost',
            port=9090,
            proto_factory=proto_factory()
        )
        server.serve()

    proc = Process(target=do_server)
    proc.start()
    time.sleep(0.25)
    msg = "exception raised!"
    with pytest.raises(TestException)as e:
        client = server_func[1](
            test_thrift.TestService,
            host='localhost',
            port=9090,
            proto_factory=proto_factory()
        )
        client.do_error(msg)
    assert e.value.message == msg

    proc.terminate()
    time.sleep(1)


@pytest.mark.parametrize('proto_factory', protocols)
def test_complex_binary(proto_factory):

    spec = thriftpy2.load("bin_test.thrift", module_name="bin_thrift")
    bin_test_obj = spec.BinTest(
        tbinary=b'\x01\x0f\xffa binary string\x0f\xee',
        str2bin={
            'key': 'value',
            'foo': 'bar'
        },
        bin2bin={
            b'bin_key': b'bin_val',
            'str2bytes': b'bin bar'
        },
        bin2str={
            b'bin key': 'str val',
        },
        binlist=[b'bin one', b'bin two', 'str should become bin'],
        binset={b'val 1', b'foo', b'bar', b'baz'},
        map_of_str2binlist={
            'key1': [b'bin 1', b'pop 2']
        },
        map_of_bin2bin={
            b'abc': {
                b'def': b'val',
                b'\x1a\x04': b'\x45'
            }
        },
        list_of_bin2str=[
            {
                b'bin key': 'str val',
                b'other key\x04': 'bob'
            }
        ]
    )

    class Handler(object):
        @staticmethod
        def test(t):
            return t

    trans_factory = TBufferedTransportFactory

    def run_server():
        server = make_rpc_server(
            spec.BinService,
            handler=Handler(),
            host='localhost',
            port=9090,
            proto_factory=proto_factory(),
            trans_factory=trans_factory(),
        )
        server.serve()

    proc = Process(target=run_server)
    proc.start()
    time.sleep(0.2)

    try:
        client = make_rpc_client(
            spec.BinService,
            host='localhost',
            port=9090,
            proto_factory=proto_factory(),
            trans_factory=trans_factory(),
        )
        res = client.test(bin_test_obj)
        check_types(spec.BinTest.thrift_spec, res)
    finally:
        proc.terminate()
    time.sleep(0.2)


@pytest.mark.skipif(cybin is None, reason="Must be run in cpython")
def test_complex_map():
    """
    Test from #156
    """
    proto = cybin
    b1 = TCyMemoryBuffer()
    proto.write_val(b1, TType.MAP, {"hello": "1"},
                    spec=(TType.STRING, TType.STRING))
    b1.flush()

    b2 = TCyMemoryBuffer()
    proto.write_val(b2, TType.MAP, {"hello": b"1"},
                    spec=(TType.STRING, TType.BINARY))
    b2.flush()

    assert b1.getvalue() != b2.getvalue()


type_map = {
    TType.BYTE: (int,),
    TType.I16: (int,),
    TType.I32: (int,),
    TType.I64: (int,),
    TType.DOUBLE: (float,),
    TType.STRING: six.string_types,
    TType.BOOL: (bool,),
    TType.STRUCT: TPayloadMeta,
    TType.SET: (set, list),
    TType.LIST: (list,),
    TType.MAP: (dict,),
    TType.BINARY: six.binary_type
}

type_names = {
    TType.BYTE: "Byte",
    TType.I16: "I16",
    TType.I32: "I32",
    TType.I64: "I64",
    TType.DOUBLE: "Double",
    TType.STRING: "String",
    TType.BOOL: "Bool",
    TType.STRUCT: "Struct",
    TType.SET: "Set",
    TType.LIST: "List",
    TType.MAP: "Map",
    TType.BINARY: "Binary"
}


def check_types(spec, val):
    """
    This function should check if a given thrift object matches
    a thrift spec
    Nb. This function isn't complete

    """
    if isinstance(spec, int):
        assert isinstance(val, type_map.get(spec))
    elif isinstance(spec, tuple):
        if len(spec) >= 2:
            if spec[0] in (TType.LIST, TType.SET):
                for item in val:
                    check_types(spec[1], item)
    else:
        for i in spec.values():
            t, field_name, to_type = i[:3]
            value = getattr(val, field_name)
            assert isinstance(value, type_map.get(t)), \
                "Field {} expected {} got {}".format(
                    field_name, type_names.get(t), type(value))
            if to_type:
                if t in (TType.SET, TType.LIST):
                    for _val in value:
                        check_types(to_type, _val)
                elif t == TType.MAP:
                    for _key, _val in value.items():
                        check_types(to_type[0], _key)
                        check_types(to_type[1], _val)
                elif t == TType.STRUCT:
                    check_types(to_type, value)
