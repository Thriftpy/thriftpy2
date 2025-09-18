import sys
import time

import pytest

import multiprocess
import thriftpy2
from thriftpy2.rpc import make_client, make_server


class Dispatcher(object):
    def Test(self, req):
        print("Get req msg: %s" % req)

        assert req == "Hello!"


class TestOneway(object):

    oneway_thrift = thriftpy2.load("oneway.thrift")

    def setup_class(self):
        server = make_server(self.oneway_thrift.echo, Dispatcher(), '127.0.0.1', 6000)
        self.p = multiprocess.Process(target=server.serve)
        self.p.start()
        time.sleep(1)  # Wait a second for server to start.

    def teardown_class(self):
        self.p.terminate()

    def test_echo(self):
        req = "Hello!"
        client = make_client(self.oneway_thrift.echo, '127.0.0.1', 6000)

        assert client.Test(req) == None
