"""Gunicorn worker classes for serving ThriftPy2 processors.

Write a module that exposes a processor::

    # app.py
    import thriftpy2
    from thriftpy2.thrift import TProcessor

    pingpong_thrift = thriftpy2.load("pingpong.thrift")

    class Dispatcher:
        def ping(self):
            return "pong"

    app = TProcessor(pingpong_thrift.PingService, Dispatcher())

and run it with the stock gunicorn command line::

    gunicorn -k thriftpy2.contrib.gunicorn.ThriftSyncWorker app:app

The application object can be a processor instance, or a zero argument
callable returning one. Gunicorn itself only accepts callables when
``--preload`` is used, so the callable form is required there.

``ThriftAsyncWorker`` serves a ``TAsyncProcessor`` from
``thriftpy2.contrib.aio`` on an asyncio event loop, handling many
connections per worker process.

Protocol and transport factories default to binary over buffered and can be
changed by subclassing a worker and overriding ``proto_factory`` and
``trans_factory``, then pointing ``-k`` at the subclass.
"""

from .sync import ThriftSyncWorker
from .aio import ThriftAsyncWorker

__all__ = ["ThriftSyncWorker", "ThriftAsyncWorker"]
