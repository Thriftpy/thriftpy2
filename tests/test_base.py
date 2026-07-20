import linecache
from pathlib import Path

import thriftpy2
from thriftpy2.thrift import parse_spec, TPayload, TType
from thriftpy2.utils import deserialize, serialize

TEST_DIR = Path(__file__).parent


def test_obj_equalcheck():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")
    ab2 = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    assert ab.Person(name="hello") == ab2.Person(name="hello")


def test_exc_equalcheck():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    assert ab.PersonNotExistsError("exc") != ab.PersonNotExistsError("exc")


def test_cls_equalcheck():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")
    ab2 = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    assert ab.Person == ab2.Person


def test_isinstancecheck():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")
    ab2 = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    assert isinstance(ab.Person(), ab2.Person)
    assert isinstance(ab.Person(name="hello"), ab2.Person)

    assert isinstance(ab.PersonNotExistsError(), ab2.PersonNotExistsError)


def test_hashable():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    # exception is hashable
    hash(ab.PersonNotExistsError("test error"))

    # struct is hashable
    hash(ab.Person(name="Tom"))

    # struct with container fields is hashable
    hash(ab.Person(name="Tom", phones=[ab.PhoneNumber(number="123")]))


def test_hash_consistent_with_eq():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    p1 = ab.Person(name="Tom", phones=[ab.PhoneNumber(number="123")])
    p2 = ab.Person(name="Tom", phones=[ab.PhoneNumber(number="123")])
    assert p1 == p2
    assert hash(p1) == hash(p2)
    assert len({p1, p2}) == 1

    # exceptions still compare and hash by identity
    e1 = ab.PersonNotExistsError("exc")
    e2 = ab.PersonNotExistsError("exc")
    assert len({e1, e2}) == 2


def test_struct_as_map_key():
    class Point(TPayload):
        thrift_spec = {
            1: (TType.I32, "x", False),
            2: (TType.I32, "y", False),
        }
        default_spec = [("x", None), ("y", None)]

    class Board(TPayload):
        thrift_spec = {
            1: (TType.MAP, "labels",
                ((TType.STRUCT, Point), TType.STRING), False),
        }
        default_spec = [("labels", None)]

    board = Board(labels={Point(x=1, y=2): "start", Point(x=3, y=4): "end"})
    result = deserialize(Board(), serialize(board))
    assert result == board
    assert result.labels[Point(x=1, y=2)] == "start"


def test_default_value():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    assert ab.PhoneNumber().type == ab.PhoneType.MOBILE


def test_parse_spec():
    ab = thriftpy2.load(TEST_DIR / "addressbook.thrift")

    cases = [
        ((TType.I32, None), "I32"),
        ((TType.STRUCT, ab.PhoneNumber), "PhoneNumber"),
        ((TType.LIST, TType.I32), "LIST<I32>"),
        ((TType.LIST, (TType.STRUCT, ab.PhoneNumber)), "LIST<PhoneNumber>"),
        ((TType.MAP, (TType.STRING, (
            TType.LIST, (TType.MAP, (TType.STRING, TType.STRING))))),
         "MAP<STRING, LIST<MAP<STRING, STRING>>>")
    ]

    for spec, res in cases:
        assert parse_spec(*spec) == res


def test_init_func():
    thriftpy2.load(TEST_DIR / "addressbook.thrift")
    assert linecache.getline('<generated PhoneNumber.__init__>', 1) != ''
