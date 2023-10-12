import multiprocessing
import thriftpy2
import time
from thriftpy2.rpc import make_client, make_server


class Dispatcher(object):
    def Test(self, req):
        print("Get req msg: %s" % req)

        assert req == "Hello!"


oneway_thrift = thriftpy2.load("oneway.thrift", module_name="oneway_thrift")
multiprocessing.set_start_method("fork")


class TestOneway(object):
    def setup_class(self):
        server = make_server(oneway_thrift.echo, Dispatcher(), '127.0.0.1', 6000)
        self.p = multiprocessing.Process(target=server.serve)
        self.p.start()
        time.sleep(1)  # Wait a second for server to start.

    def teardown_class(self):
        self.p.terminate()

    def test_echo(self):
        req = "Hello!"
        client = make_client(oneway_thrift.echo, '127.0.0.1', 6000)

        assert client.Test(req) == None
