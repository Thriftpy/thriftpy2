"""Application module used by test_gunicorn.py, loaded by gunicorn."""
import os

import thriftpy2
from thriftpy2.contrib.aio.processor import TAsyncProcessor
from thriftpy2.thrift import TProcessor

addressbook = thriftpy2.load(
    os.path.join(os.path.dirname(__file__), "addressbook.thrift"))


class Dispatcher:
    def ping(self):
        pass

    def hello(self, name):
        return "hello " + name


class AsyncDispatcher:
    async def ping(self):
        pass

    async def hello(self, name):
        return "hello " + name


app = TProcessor(addressbook.AddressBookService, Dispatcher())
aio_app = TAsyncProcessor(addressbook.AddressBookService, AsyncDispatcher())


def factory():
    return app
