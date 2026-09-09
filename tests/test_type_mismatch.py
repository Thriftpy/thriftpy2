from unittest import TestCase, expectedFailure

from thriftpy2.thrift import TType, TPayload

from thriftpy2.transport.memory import TMemoryBuffer
from thriftpy2.protocol.binary import TBinaryProtocol
from thriftpy2.protocol.compact import TCompactProtocol

from thriftpy2._compat import CYTHON


class Struct(TPayload):
    thrift_spec = {
        1: (TType.I32, 'a', False),
        2: (TType.STRING, 'b', False),
        3: (TType.DOUBLE, 'c', False)
    }
    default_spec = [('a', None), ('b', None), ('c', None)]


class TItem(TPayload):
    thrift_spec = {
        1: (TType.I32, "id", False),
        2: (TType.LIST, "phones", TType.STRING, False),
        3: (TType.MAP, "addr", (TType.I32, TType.STRING), False),
        4: (TType.LIST, "data", (TType.STRUCT, Struct), False)
    }
    default_spec = [("id", None), ("phones", None), ("addr", None),
                    ("data", None)]


class MismatchTestCase(TestCase):
    BUFFER = TMemoryBuffer
    PROTO = TBinaryProtocol

    def test_list_type_mismatch(self):
        class TMismatchItem(TPayload):
            thrift_spec = {
                1: (TType.I32, "id", False),
                2: (TType.LIST, "phones", (TType.I32, False), False),
            }
            default_spec = [("id", None), ("phones", None)]

        t = self.BUFFER()
        p = self.PROTO(t)

        item = TItem(id=37, phones=["23424", "235125"])
        p.write_struct(item)
        p.write_message_end()

        item2 = TMismatchItem()
        p.read_struct(item2)

        assert item2.phones == []

    def test_map_type_mismatch(self):
        class TMismatchItem(TPayload):
            thrift_spec = {
                1: (TType.I32, "id", False),
                3: (TType.MAP, "addr", (TType.STRING, TType.STRING), False)
            }
            default_spec = [("id", None), ("addr", None)]

        t = self.BUFFER()
        p = self.PROTO(t)

        item = TItem(id=37, addr={1: "hello", 2: "world"})
        p.write_struct(item)
        p.write_message_end()

        item2 = TMismatchItem()
        p.read_struct(item2)

        assert item2.addr == {}

    def test_map_type_mismatch_with_string_on_wire(self):
        class TWireItem(TPayload):
            thrift_spec = {
                1: (TType.MAP, "addr", (TType.STRING, TType.I32), False),
                2: (TType.I32, "x", False),
            }
            default_spec = [("addr", None), ("x", None)]

        class TMismatchItem(TPayload):
            thrift_spec = {
                1: (TType.MAP, "addr", (TType.I32, TType.I32), False),
                2: (TType.I32, "x", False),
            }
            default_spec = [("addr", None), ("x", None)]

        t = self.BUFFER()
        p = self.PROTO(t)

        p.write_struct(TWireItem(addr={"abcd": 1, "efgh": 2}, x=5))
        p.write_message_end()

        item2 = TMismatchItem()
        p.read_struct(item2)

        assert item2.addr == {}
        assert item2.x == 5

    def test_struct_mismatch(self):
        class MismatchStruct(TPayload):
            thrift_spec = {
                1: (TType.STRING, 'a', False),
                2: (TType.STRING, 'b', False)
            }
            default_spec = [('a', None), ('b', None)]

        class TMismatchItem(TPayload):
            thrift_spec = {
                1: (TType.I32, "id", False),
                2: (TType.LIST, "phones", TType.STRING, False),
                3: (TType.MAP, "addr", (TType.I32, TType.STRING), False),
                4: (TType.LIST, "data", (TType.STRUCT, MismatchStruct), False)
            }
            default_spec = [("id", None), ("phones", None), ("addr", None)]

        t = self.BUFFER()
        p = self.PROTO(t)

        item = TItem(id=37, data=[Struct(a=1, b="hello", c=0.123),
                                  Struct(a=2, b="world", c=34.342346),
                                  Struct(a=3, b="when", c=25235.14)])
        p.write_struct(item)
        p.write_message_end()

        item2 = TMismatchItem()
        p.read_struct(item2)

        assert len(item2.data) == 3
        assert all([i.b for i in item2.data])


class CompactMismatchTestCase(MismatchTestCase):
    PROTO = TCompactProtocol

    # The compact protocol does not check list element types yet.
    @expectedFailure
    def test_list_type_mismatch(self):
        super().test_list_type_mismatch()


if CYTHON:
    from thriftpy2.transport.memory import TCyMemoryBuffer
    from thriftpy2.protocol.cybin import TCyBinaryProtocol

    class CyMismatchTestCase(MismatchTestCase):
        BUFFER = TCyMemoryBuffer
        PROTO = TCyBinaryProtocol
