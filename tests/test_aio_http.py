import asyncio
import os
import random
import threading
import time

import pytest

import thriftpy2
from thriftpy2.contrib.aio.protocol import (
    TAsyncBinaryProtocolFactory,
    TAsyncCompactProtocolFactory
)
from thriftpy2.contrib.aio.http import (
    make_client, make_server, client_context,
    TAsyncHttpHeaderFactory
)


addressbook = thriftpy2.load(
    os.path.join(os.path.dirname(__file__), "addressbook.thrift")
)


class Dispatcher:
    def __init__(self):
        self.ab = addressbook.AddressBook()
        self.ab.people = {}
        self.custom_headers = None

    async def ping(self):
        return True

    async def hello(self, name):
        return "hello " + name

    async def add(self, person):
        self.ab.people[person.name] = person
        return True

    async def remove(self, name):
        if not name:
            raise ValueError('name cannot be empty')
        try:
            self.ab.people.pop(name)
            return True
        except KeyError:
            raise addressbook.PersonNotExistsError(
                "{0} not exists".format(name))

    async def get(self, name):
        try:
            return self.ab.people[name]
        except KeyError:
            raise addressbook.PersonNotExistsError(
                "{0} not exists".format(name))

    async def book(self):
        return self.ab

    async def get_phonenumbers(self, name, count):
        p = [self.ab.people[name].phones[0]] if name in self.ab.people else []
        return p * count

    async def get_phones(self, name):
        phone_numbers = self.ab.people[name].phones
        return dict((p.type, p.number) for p in phone_numbers)

    async def sleep(self, ms):
        await asyncio.sleep(ms / 1000.0)
        return True


def _create_person():
    phone1 = addressbook.PhoneNumber()
    phone1.type = addressbook.PhoneType.MOBILE
    phone1.number = '555-1212'
    phone2 = addressbook.PhoneNumber()
    phone2.type = addressbook.PhoneType.HOME
    phone2.number = '555-1234'

    alice = addressbook.Person()
    alice.name = "Alice"
    alice.phones = [phone1, phone2]
    alice.created_at = int(time.time())

    return alice


class _TestAsyncHttp:
    PROTOCOL_FACTORY = TAsyncBinaryProtocolFactory()

    @classmethod
    def setup_class(cls):
        cls.port = random.randint(57000, 58000)
        cls.person = _create_person()
        cls._start_server()

    @classmethod
    def teardown_class(cls):
        cls._stop_server()

    @classmethod
    def _start_server(cls):
        cls._server_loop = asyncio.new_event_loop()
        cls.server = make_server(
            addressbook.AddressBookService,
            Dispatcher(),
            host='127.0.0.1',
            port=cls.port,
            proto_factory=cls.PROTOCOL_FACTORY
        )

        async def run_server():
            await cls.server.serve()

        def server_thread():
            asyncio.set_event_loop(cls._server_loop)
            try:
                cls._server_loop.run_until_complete(run_server())
            except asyncio.CancelledError:
                pass

        cls._server_thread = threading.Thread(target=server_thread, daemon=True)
        cls._server_thread.start()
        time.sleep(0.3)  # Wait for server to start

    @classmethod
    def _stop_server(cls):
        async def stop():
            await cls.server.close()

        cls._server_loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(stop(), loop=cls._server_loop)
        )
        cls._server_loop.call_soon_threadsafe(cls._server_loop.stop)
        cls._server_thread.join(timeout=2)

    async def client(self, timeout=30000):
        return await make_client(
            addressbook.AddressBookService,
            host='127.0.0.1',
            port=self.port,
            proto_factory=self.PROTOCOL_FACTORY,
            timeout=timeout
        )

    @pytest.mark.asyncio
    async def test_void_api(self):
        c = await self.client()
        result = await c.ping()
        assert result is None  # void method returns None
        c.close()

    @pytest.mark.asyncio
    async def test_string_api(self):
        c = await self.client()
        assert await c.hello("world") == "hello world"
        c.close()

    @pytest.mark.asyncio
    async def test_huge_response(self):
        c = await self.client()
        big_str = "world" * 10000
        assert await c.hello(big_str) == "hello " + big_str
        c.close()

    @pytest.mark.asyncio
    async def test_tstruct_req(self):
        c = await self.client()
        assert await c.add(self.person) is True
        c.close()

    @pytest.mark.asyncio
    async def test_tstruct_res(self):
        c = await self.client()
        await c.add(self.person)
        result = await c.get("Alice")
        assert self.person.name == result.name
        c.close()

    @pytest.mark.asyncio
    async def test_exception(self):
        c = await self.client()
        with pytest.raises(addressbook.PersonNotExistsError):
            await c.remove("Bob")
        c.close()

    @pytest.mark.asyncio
    async def test_client_context(self):
        async with client_context(
            addressbook.AddressBookService,
            host='127.0.0.1',
            port=self.port,
            proto_factory=self.PROTOCOL_FACTORY
        ) as c:
            assert await c.hello("context") == "hello context"

    @pytest.mark.asyncio
    async def test_url_param(self):
        c = await make_client(
            addressbook.AddressBookService,
            url='http://127.0.0.1:{}/'.format(self.port),
            proto_factory=self.PROTOCOL_FACTORY
        )
        assert await c.hello("url") == "hello url"
        c.close()


class TestAsyncHttpBinary(_TestAsyncHttp):
    PROTOCOL_FACTORY = TAsyncBinaryProtocolFactory()


class TestAsyncHttpCompact(_TestAsyncHttp):
    PROTOCOL_FACTORY = TAsyncCompactProtocolFactory()


class TestAsyncHttpTimeout:
    @classmethod
    def setup_class(cls):
        cls.port = random.randint(58000, 59000)
        cls._start_server()

    @classmethod
    def teardown_class(cls):
        cls._stop_server()

    @classmethod
    def _start_server(cls):
        cls._server_loop = asyncio.new_event_loop()
        cls.server = make_server(
            addressbook.AddressBookService,
            Dispatcher(),
            host='127.0.0.1',
            port=cls.port
        )

        async def run_server():
            await cls.server.serve()

        def server_thread():
            asyncio.set_event_loop(cls._server_loop)
            try:
                cls._server_loop.run_until_complete(run_server())
            except asyncio.CancelledError:
                pass

        cls._server_thread = threading.Thread(target=server_thread, daemon=True)
        cls._server_thread.start()
        time.sleep(0.3)

    @classmethod
    def _stop_server(cls):
        async def stop():
            await cls.server.close()

        cls._server_loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(stop(), loop=cls._server_loop)
        )
        cls._server_loop.call_soon_threadsafe(cls._server_loop.stop)
        cls._server_thread.join(timeout=2)

    @pytest.mark.asyncio
    async def test_timeout(self):
        c = await make_client(
            addressbook.AddressBookService,
            host='127.0.0.1',
            port=self.port,
            timeout=500  # 500ms timeout
        )
        # Request should timeout
        with pytest.raises(asyncio.TimeoutError):
            await c.sleep(2000)  # Sleep 2 seconds
        c.close()


class TestAsyncHttpCustomHeaders:
    @classmethod
    def setup_class(cls):
        cls.port = random.randint(59000, 60000)
        cls._start_server()

    @classmethod
    def teardown_class(cls):
        cls._stop_server()

    @classmethod
    def _start_server(cls):
        cls._server_loop = asyncio.new_event_loop()
        cls.server = make_server(
            addressbook.AddressBookService,
            Dispatcher(),
            host='127.0.0.1',
            port=cls.port
        )

        async def run_server():
            await cls.server.serve()

        def server_thread():
            asyncio.set_event_loop(cls._server_loop)
            try:
                cls._server_loop.run_until_complete(run_server())
            except asyncio.CancelledError:
                pass

        cls._server_thread = threading.Thread(target=server_thread, daemon=True)
        cls._server_thread.start()
        time.sleep(0.3)

    @classmethod
    def _stop_server(cls):
        async def stop():
            await cls.server.close()

        cls._server_loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(stop(), loop=cls._server_loop)
        )
        cls._server_loop.call_soon_threadsafe(cls._server_loop.stop)
        cls._server_thread.join(timeout=2)

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        header_factory = TAsyncHttpHeaderFactory({
            'X-Custom-Header': 'custom-value',
            'Authorization': 'Bearer token123'
        })
        c = await make_client(
            addressbook.AddressBookService,
            host='127.0.0.1',
            port=self.port,
            http_header_factory=header_factory
        )
        # Just verify the request works with custom headers
        assert await c.hello("headers") == "hello headers"
        c.close()

    @pytest.mark.asyncio
    async def test_header_factory_get_headers(self):
        headers = {'X-Test': 'test-value'}
        factory = TAsyncHttpHeaderFactory(headers)
        assert factory.get_headers() == headers

    @pytest.mark.asyncio
    async def test_empty_header_factory(self):
        factory = TAsyncHttpHeaderFactory()
        assert factory.get_headers() == {}
