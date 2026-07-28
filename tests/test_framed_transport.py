import contextlib
import socket
import threading
import time

from os import path
from unittest import TestCase

import thriftpy2
from thriftpy2._compat import CYTHON
from thriftpy2.protocol.binary import TBinaryProtocolFactory
from thriftpy2.rpc import client_context, make_server
from thriftpy2.transport.framed import TFramedTransportFactory


addressbook = thriftpy2.load(path.join(path.dirname(__file__),
                                       "addressbook.thrift"))


class Dispatcher(object):
    def __init__(self):
        self.registry = {}

    def add(self, person):
        """
        bool add(1: Person person);
        """
        if person.name in self.registry:
            return False
        self.registry[person.name] = person
        return True

    def get(self, name):
        """
        Person get(1: string name)
        """
        if name not in self.registry:
            raise addressbook.PersonNotExistsError()
        return self.registry[name]


class FramedTransportTestCase(TestCase):
    TRANSPORT_FACTORY = TFramedTransportFactory()
    PROTOCOL_FACTORY = TBinaryProtocolFactory()

    def mk_client(self):
        return client_context(
            addressbook.AddressBookService,
            "127.0.0.1",
            self.port,
            proto_factory=self.PROTOCOL_FACTORY,
            trans_factory=self.TRANSPORT_FACTORY,
        )

    def mk_client_with_url(self):
        return client_context(
            addressbook.AddressBookService,
            proto_factory=self.PROTOCOL_FACTORY,
            trans_factory=self.TRANSPORT_FACTORY,
            url="thrift://127.0.0.1:{port}".format(port=self.port),
        )

    def setUp(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[-1]

        self.server = make_server(
            addressbook.AddressBookService,
            Dispatcher(),
            host="127.0.0.1",
            port=self.port,
            proto_factory=self.PROTOCOL_FACTORY,
            trans_factory=self.TRANSPORT_FACTORY,
        )
        self.server.daemon = True
        self.server_thread = threading.Thread(
            target=self.server.serve, daemon=True
        )
        self.server_thread.start()
        time.sleep(0.1)

        self.clients = contextlib.ExitStack()
        self.client = self.clients.enter_context(self.mk_client())
        self.client_created_using_url = self.clients.enter_context(
            self.mk_client_with_url()
        )

    def tearDown(self):
        self.clients.close()
        self.server.close()
        self.server.trans.close()
        self.server_thread.join(timeout=1)

    def test_make_client(self):
        linus = addressbook.Person("Linus Torvalds")
        success = self.client_created_using_url.add(linus)
        assert success
        success = self.client.add(linus)
        assert not success

    def test_able_to_communicate(self):
        dennis = addressbook.Person(name="Dennis Ritchie")
        success = self.client.add(dennis)
        assert success
        success = self.client.add(dennis)
        assert not success

    def test_zero_length_string(self):
        dennis = addressbook.Person(name="")
        success = self.client.add(dennis)
        assert success
        success = self.client.get(name="")
        assert success


if CYTHON:
    from thriftpy2.protocol.cybin import TCyBinaryProtocolFactory
    from thriftpy2.transport.framed import TCyFramedTransportFactory

    class CyFramedTransportTestCase(FramedTransportTestCase):
        PROTOCOL_FACTORY = TCyBinaryProtocolFactory()
        TRANSPORT_FACTORY = TCyFramedTransportFactory()
