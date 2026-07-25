"""Regression tests for out of order field IDs (issue #367).

Arguments must be mapped by IDL declaration order, not by field ID,
to stay compatible with Apache Thrift generated code.
"""

import multiprocessing
import sys
import time
from pathlib import Path

import pytest

import thriftpy2
from thriftpy2.rpc import make_client, make_server
from thriftpy2.thrift import TType, args_to_kwargs

TEST_DIR = Path(__file__).parent
PORT = 50442


def test_args_to_kwargs_declaration_order():
    spec = {
        1: (TType.STRING, "a", True),
        3: (TType.STRING, "b", True),
        2: (TType.STRING, "c", True),
    }
    assert args_to_kwargs(spec, "x", "y", "z") == \
        {"a": "x", "b": "y", "c": "z"}
    assert args_to_kwargs(spec, "x", c="z", b="y") == \
        {"a": "x", "b": "y", "c": "z"}


@pytest.mark.skipif(sys.platform == "win32", reason="requires fork")
class TestOutOfOrderFieldsRPC(object):

    hello_thrift = thriftpy2.load(TEST_DIR / "out_of_order_fields.thrift")

    class Dispatcher(object):
        def say_hello(self, a, b, c):
            return "%s %s %s" % (a, b, c)

    def setup_class(self):
        ctx = multiprocessing.get_context("fork")
        server = make_server(self.hello_thrift.HelloService,
                             self.Dispatcher(), "127.0.0.1", PORT)
        self.p = ctx.Process(target=server.serve)
        self.p.start()
        time.sleep(1)  # Wait a second for server to start.

    def teardown_class(self):
        self.p.terminate()

    def test_positional_args(self):
        client = make_client(self.hello_thrift.HelloService,
                             "127.0.0.1", PORT)
        assert client.say_hello("x", "y", "z") == "x y z"

    def test_keyword_args(self):
        client = make_client(self.hello_thrift.HelloService,
                             "127.0.0.1", PORT)
        assert client.say_hello(a="x", b="y", c="z") == "x y z"

    def test_mixed_args(self):
        client = make_client(self.hello_thrift.HelloService,
                             "127.0.0.1", PORT)
        assert client.say_hello("x", c="z", b="y") == "x y z"
