from pathlib import Path

from thriftpy2 import load
from thriftpy2.thrift import TType

TEST_DIR = Path(__file__).parent


def test_set():
    s = load(TEST_DIR / "type.thrift")

    assert s.Set.thrift_spec == {1: (TType.SET, "a_set", TType.STRING, True)}
