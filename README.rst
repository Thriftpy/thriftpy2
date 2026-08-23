=========
ThriftPy2
=========

.. image:: https://img.shields.io/codecov/c/github/Thriftpy/thriftpy2.svg
    :target: https://codecov.io/gh/Thriftpy/thriftpy2

.. image:: https://img.shields.io/pypi/dm/thriftpy2.svg
    :target: https://pypi.org/project/thriftpy2/

.. image:: https://img.shields.io/pypi/v/thriftpy2.svg
    :target: https://pypi.org/project/thriftpy2/

.. image:: https://img.shields.io/pypi/pyversions/thriftpy2.svg
    :target: https://pypi.org/project/thriftpy2/

.. image:: https://img.shields.io/pypi/implementation/thriftpy2.svg
    :target: https://pypi.org/project/thriftpy2/


ThriftPy2 is a pure Python implementation of the `Apache Thrift <https://thrift.apache.org/>`_
protocol. It allows you to parse Thrift IDL files and create RPC clients/servers
without code generation or compilation.


Installation
============

Install with pip:

.. code:: bash

    $ pip install thriftpy2


Features
========

- Python 3.10+ and PyPy3.

- Pure Python implementation. No need to compile or install the ``thrift`` package.
  All you need is thriftpy2 and a thrift file.

- Dynamically load thrift files as Python modules, with code generated on the fly.

- Compatible with Apache Thrift. You can use ThriftPy2 together with the
  official implementation servers and clients.

- Easy RPC server/client setup.

- Supported protocols and transports:

  * binary protocol (Python and Cython)
  * compact protocol (Python and Cython)
  * JSON protocol
  * Apache JSON protocol
  * buffered transport (Python and Cython)
  * framed transport
  * HTTP server and client
  * asyncio support


Quick Start
===========

Define a ``pingpong.thrift`` file:

::

    service PingPong {
        string ping(),
    }

Server
------

.. code:: python

    import thriftpy2
    from thriftpy2.rpc import make_server

    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")


    class Dispatcher(object):
        def ping(self):
            return "pong"


    server = make_server(pingpong_thrift.PingPong, Dispatcher(), '127.0.0.1', 6000)
    server.serve()

Client
------

.. code:: python

    import thriftpy2
    from thriftpy2.rpc import make_client

    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")

    client = make_client(pingpong_thrift.PingPong, '127.0.0.1', 6000)
    print(client.ping())  # prints "pong"

Async Server
------------

.. code:: python

    import thriftpy2
    from thriftpy2.rpc import make_aio_server

    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")


    class Dispatcher(object):
        async def ping(self):
            return "pong"


    server = make_aio_server(pingpong_thrift.PingPong, Dispatcher(), '127.0.0.1', 6000)
    server.serve()

Async Client
------------

.. code:: python

    import asyncio
    import thriftpy2
    from thriftpy2.rpc import make_aio_client

    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")


    async def main():
        client = await make_aio_client(pingpong_thrift.PingPong, '127.0.0.1', 6000)
        print(await client.ping())  # prints "pong"
        client.close()


    if __name__ == '__main__':
        asyncio.run(main())

Gunicorn
--------

``thriftpy2.contrib.gunicorn`` provides worker classes so a processor can be
served by gunicorn, with its multi process management, graceful reload and
the rest of its features. Expose a processor in a module:

.. code:: python

    # app.py
    import thriftpy2
    from thriftpy2.thrift import TProcessor

    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")


    class Dispatcher(object):
        def ping(self):
            return "pong"


    app = TProcessor(pingpong_thrift.PingPong, Dispatcher())

and start it with the gunicorn command:

.. code:: bash

    gunicorn -k thriftpy2.contrib.gunicorn.ThriftSyncWorker -w 4 -b 127.0.0.1:6000 app:app

``ThriftSyncWorker`` handles one connection at a time per worker process.
``ThriftAsyncWorker`` serves a ``TAsyncProcessor`` with async handlers on an
asyncio event loop and handles many connections per process. Idle
connections are closed after ``--keep-alive`` seconds, and ``--max-requests``
counts thrift calls. The protocol and transport default to binary over
buffered. To use others, subclass a worker and override ``proto_factory``
and ``trans_factory``, which can be done right in the gunicorn config file:

.. code:: python

    # gunicorn.conf.py
    from thriftpy2.contrib.gunicorn import ThriftSyncWorker
    from thriftpy2.protocol import TCompactProtocolFactory
    from thriftpy2.transport import TFramedTransportFactory


    class Worker(ThriftSyncWorker):
        proto_factory = TCompactProtocolFactory()
        trans_factory = TFramedTransportFactory()


    worker_class = Worker

.. code:: bash

    gunicorn -c gunicorn.conf.py -w 4 -b 127.0.0.1:6000 app:app

See the ``examples`` and ``tests`` directories for more usage examples.


Migrate from ThriftPy
=====================

ThriftPy (https://github.com/eleme/thriftpy) has been deprecated.
ThriftPy2 is fully compatible, just change your import:

.. code:: python

    import thriftpy2 as thriftpy


Contribute
==========

1. Fork the repo and make changes.

2. Write a test that shows a bug was fixed or the feature works as expected.

3. Make sure ``tox`` tests succeed.

4. Send a pull request.


Contributors
============

https://github.com/Thriftpy/thriftpy2/graphs/contributors


Sponsors
========

.. image:: ./docs/jetbrains.svg
    :target: https://www.jetbrains.com/?from=ThriftPy


Changelog
=========

https://github.com/Thriftpy/thriftpy2/releases
