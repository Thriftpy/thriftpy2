import asyncio
import os
import signal
import subprocess
import sys
import time

import pytest

import thriftpy2
from thriftpy2.rpc import make_aio_client, make_client
from thriftpy2.transport import TTransportException

from _helpers import free_port, wait_for_port

pytest.importorskip("gunicorn")

if sys.platform == "win32":
    pytest.skip("gunicorn does not run on Windows", allow_module_level=True)

TEST_DIR = os.path.dirname(__file__)
addressbook = thriftpy2.load(os.path.join(TEST_DIR, "addressbook.thrift"))

SYNC = "thriftpy2.contrib.gunicorn.ThriftSyncWorker"
ASYNC = "thriftpy2.contrib.gunicorn.ThriftAsyncWorker"


class Gunicorn:
    def __init__(self, worker, app="gunicorn_app:app", *extra):
        self.port = free_port()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "gunicorn",
             *(["-k", worker] if worker else []),
             "-b", f"127.0.0.1:{self.port}", "--chdir", TEST_DIR,
             "--log-level", "debug", *extra, app],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            wait_for_port(self.port, timeout=15)
        except Exception:
            self.stop()
            raise RuntimeError(self.output)

    def stop(self):
        if self.proc.stdout.closed:
            return self.output
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.output = self.proc.stdout.read()
        self.proc.stdout.close()
        return self.output

    def client(self, **kwargs):
        return make_client(addressbook.AddressBookService, "127.0.0.1",
                           self.port, **kwargs)


@pytest.fixture(params=[SYNC, ASYNC], ids=["sync", "async"])
def server(request):
    app = "gunicorn_app:aio_app" if request.param == ASYNC \
        else "gunicorn_app:app"
    srv = Gunicorn(request.param, app, "--keep-alive", "60")
    yield srv
    srv.stop()


def test_rpc(server):
    client = server.client()
    try:
        client.ping()
        assert client.hello("world") == "hello world"
        assert client.hello("again") == "hello again"
    finally:
        client.close()


def test_several_connections(server):
    for _ in range(3):
        client = server.client()
        try:
            assert client.hello("x") == "hello x"
        finally:
            client.close()


@pytest.mark.parametrize("worker, app", [
    (SYNC, "gunicorn_app:app"), (ASYNC, "gunicorn_app:aio_app")],
    ids=["sync", "async"])
def test_idle_connection_closed(worker, app):
    srv = Gunicorn(worker, app, "--keep-alive", "1")
    try:
        client = srv.client(timeout=5000)
        assert client.hello("x") == "hello x"
        time.sleep(2)
        with pytest.raises(TTransportException):
            client.hello("y")
        client.close()
    finally:
        srv.stop()


def test_factory_app():
    srv = Gunicorn(SYNC, "gunicorn_app:factory")
    try:
        client = srv.client()
        assert client.hello("f") == "hello f"
        client.close()
    finally:
        srv.stop()


def test_factory_app_preload():
    srv = Gunicorn(SYNC, "gunicorn_app:factory", "--preload")
    try:
        client = srv.client()
        assert client.hello("p") == "hello p"
        client.close()
    finally:
        srv.stop()


def test_max_requests_restarts_worker():
    srv = Gunicorn(SYNC, "gunicorn_app:app", "--max-requests", "2",
                   "--keep-alive", "60")
    try:
        client = srv.client()
        assert client.hello("1") == "hello 1"
        assert client.hello("2") == "hello 2"
        # the worker closes the connection after the second request
        with pytest.raises(TTransportException):
            client.hello("3")
        client.close()
        wait_for_port(srv.port, timeout=15)
        client = srv.client()
        assert client.hello("4") == "hello 4"
        client.close()
    finally:
        out = srv.stop()
    assert "Autorestarting worker" in out


def test_async_worker_concurrent_clients():
    srv = Gunicorn(ASYNC, "gunicorn_app:aio_app", "--keep-alive", "60")

    async def run():
        clients = [await make_aio_client(addressbook.AddressBookService,
                                         "127.0.0.1", srv.port)
                   for _ in range(5)]
        try:
            results = await asyncio.gather(
                *(c.hello(str(i)) for i, c in enumerate(clients)))
            assert results == [f"hello {i}" for i in range(5)]
        finally:
            for c in clients:
                c.close()

    try:
        asyncio.run(run())
    finally:
        srv.stop()


def test_wrong_app_object_fails():
    port = free_port()
    proc = subprocess.run(
        [sys.executable, "-m", "gunicorn", "-k", SYNC,
         "-b", f"127.0.0.1:{port}", "--chdir", TEST_DIR,
         "gunicorn_app:addressbook"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=30)
    assert proc.returncode != 0
    assert "thrift processor" in proc.stdout


def test_async_worker_sigterm_closes_idle_connection():
    srv = Gunicorn(ASYNC, "gunicorn_app:aio_app", "--keep-alive", "60")
    client = srv.client(timeout=5000)
    try:
        assert client.hello("x") == "hello x"
        start = time.time()
        srv.proc.send_signal(signal.SIGTERM)
        srv.proc.wait(timeout=15)
        assert time.time() - start < 10
        with pytest.raises(TTransportException):
            client.hello("y")
    finally:
        client.close()
        srv.stop()


def test_custom_protocol_and_transport_from_config_file():
    from thriftpy2.protocol import TCompactProtocolFactory
    from thriftpy2.transport import TFramedTransportFactory

    srv = Gunicorn(None, "gunicorn_app:app", "-c",
                   os.path.join(TEST_DIR, "gunicorn_conf.py"))
    try:
        client = srv.client(proto_factory=TCompactProtocolFactory(),
                            trans_factory=TFramedTransportFactory())
        assert client.hello("compact") == "hello compact"
        client.close()
    finally:
        out = srv.stop()
    assert "CompactFramedWorker" in out
