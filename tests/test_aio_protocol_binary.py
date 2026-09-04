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


class TTree(TPayload):
    thrift_spec = {
        1: (TType.I32, "v", False),
        2: (TType.STRUCT, "child", None, False),
        3: (TType.LIST, "children", None, False),
    }
    default_spec = [("v", None), ("child", None), ("children", None)]


TTree.thrift_spec[2] = (TType.STRUCT, "child", TTree, False)
TTree.thrift_spec[3] = (TType.LIST, "children", (TType.STRUCT, TTree), False)


def make_tree(depth, in_list=False):
    root = TTree(v=0)
    node = root
    for i in range(1, depth + 1):
        child = TTree(v=i)
        if in_list:
            node.children = [child]
        else:
            node.child = child
        node = child
    return root


def tree_depth(obj):
    depth = 0
    while obj.child is not None or obj.children:
        obj = obj.child if obj.child is not None else obj.children[0]
        depth += 1
    return depth


def encode(obj, **kwargs):
    b = BytesIO()
    proto.TAsyncBinaryProtocol(b, **kwargs).write_struct(obj)
    return b.getvalue()


async def decode(blob, cls=TTree, **kwargs):
    obj = cls()
    b = AsyncBytesIO(BytesIO(blob))
    await proto.TAsyncBinaryProtocol(b, **kwargs).read_struct(obj)
    return obj


# The root struct counts as a level too, and the extra struct above the list
# chain makes it overflow on a list instead of a struct.
LIMIT = proto.DEFAULT_MAX_DEPTH
DEEPEST = make_tree(LIMIT - 1)
DEEPEST_LIST = make_tree((LIMIT - 2) // 2, in_list=True)
TOO_DEEP = make_tree(LIMIT)
TOO_DEEP_LIST = TTree(v=0, child=make_tree(LIMIT // 2, in_list=True))


@pytest.mark.asyncio
async def test_nested_struct_within_limit():
    assert tree_depth(await decode(encode(DEEPEST))) == LIMIT - 1
    assert tree_depth(await decode(encode(DEEPEST_LIST))) == (LIMIT - 2) // 2


def test_deeply_nested_write_raises_recursion_error():
    with pytest.raises(RecursionError, match="while writing a Thrift struct"):
        encode(TOO_DEEP)
    with pytest.raises(RecursionError,
                       match="while writing a Thrift container"):
        encode(TOO_DEEP_LIST)


@pytest.mark.asyncio
async def test_deeply_nested_read_raises_recursion_error():
    blob = encode(TOO_DEEP, max_depth=LIMIT + 8)
    with pytest.raises(RecursionError, match="while reading a Thrift struct"):
        await decode(blob)
    blob = encode(TOO_DEEP_LIST, max_depth=LIMIT + 8)
    with pytest.raises(RecursionError,
                       match="while reading a Thrift container"):
        await decode(blob)


@pytest.mark.asyncio
async def test_deeply_nested_skip_raises_recursion_error():
    # TItem has a list where TTree has its child struct, so the subtree is
    # skipped rather than read.
    blob = encode(TOO_DEEP, max_depth=LIMIT + 8)
    with pytest.raises(RecursionError, match="while skipping a Thrift struct"):
        await decode(blob, TItem)
    with pytest.raises(RecursionError):
        await proto.skip(AsyncBytesIO(BytesIO(blob)), TType.STRUCT)
    with pytest.raises(RecursionError):
        b = AsyncBytesIO(BytesIO(blob))
        await proto.TAsyncBinaryProtocol(b).skip(TType.STRUCT)

    blob = encode(TOO_DEEP_LIST, max_depth=LIMIT + 8)
    with pytest.raises(RecursionError,
                       match="while skipping a Thrift container"):
        await decode(blob, TItem)


@pytest.mark.asyncio
async def test_max_depth_is_configurable():
    depth = LIMIT * 4
    obj = make_tree(depth)
    blob = encode(obj, max_depth=depth + 1)
    assert tree_depth(await decode(blob, max_depth=depth + 1)) == depth
    await decode(blob, TItem, max_depth=depth + 1)
    b = AsyncBytesIO(BytesIO(blob))
    await proto.TAsyncBinaryProtocol(b, max_depth=depth + 1).skip(TType.STRUCT)

    with pytest.raises(RecursionError):
        encode(obj, max_depth=depth)
    with pytest.raises(RecursionError):
        await decode(blob, max_depth=depth)
    with pytest.raises(RecursionError):
        await decode(blob, TItem, max_depth=depth)

    factory = proto.TAsyncBinaryProtocolFactory(max_depth=depth + 1)
    p = factory.get_protocol(AsyncBytesIO(BytesIO(blob)))
    assert p.max_depth == depth + 1
    obj = TTree()
    await p.read_struct(obj)
    assert tree_depth(obj) == depth
