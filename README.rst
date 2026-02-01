============
ThriftPy2
============

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


ThriftPy: https://github.com/eleme/thriftpy has been deprecated. ThriftPy2 aims to provide long-term support.


Migrate from Thriftpy?
======================

All you need is:

.. code:: python

    import thriftpy2 as thriftpy


That's it! thriftpy2 is fully compatible with thriftpy.


Installation
============

Install with pip:

.. code:: bash

    $ pip install thriftpy2


Code Demo
=========

ThriftPy2 makes it super easy to write server/client code with Thrift. Let's
check out this simple pingpong service demo.

We need a `pingpong.thrift` file:

::

    service PingPong {
        string ping(),
    }

Then we can make a server:

.. code:: python

    import thriftpy2
    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")

    from thriftpy2.rpc import make_server

    class Dispatcher(object):
        def ping(self):
            return "pong"

    server = make_server(pingpong_thrift.PingPong, Dispatcher(), '127.0.0.1', 6000)
    server.serve()

And a client:

.. code:: python

    import thriftpy2
    pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")

    from thriftpy2.rpc import make_client

    client = make_client(pingpong_thrift.PingPong, '127.0.0.1', 6000)
    print(client.ping())

And it also supports asyncio on Python 3.7 or later.

We need an `echo.thrift` file:

::

    service EchoService {
        string echo(1: string param),
    }

Then we can make an async client:

.. code:: python

    import asyncio
    import thriftpy2
    from thriftpy2.rpc import make_aio_client

    echo_thrift = thriftpy2.load("echo.thrift", module_name="echo_thrift")


    async def request():
        client = await make_aio_client(
            echo_thrift.EchoService, '127.0.0.1', 6000)
        print(await client.echo('hello, world'))
        client.close()


    if __name__ == '__main__':
        asyncio.run(request())

And an async server:

.. code:: python

    import asyncio
    import thriftpy2
    from thriftpy2.rpc import make_aio_server

    echo_thrift = thriftpy2.load("echo.thrift", module_name="echo_thrift")


    class Dispatcher(object):
        async def echo(self, param):
            print(param)
            await asyncio.sleep(0.1)
            return param


    def main():
        server = make_aio_server(
            echo_thrift.EchoService, Dispatcher(), '127.0.0.1', 6000)
        server.serve()


    if __name__ == '__main__':
        main()

See, it's that easy!

You can refer to the `examples` and `tests` directories in the source code for more
usage examples.


Features
========

Currently, ThriftPy2 has these features (also advantages over the upstream
Python lib):

- Python 3.7+ and PyPy3.

- Pure Python implementation. You no longer need to compile and install the `thrift`
  package. All you need is thriftpy2 and a thrift file.

- Compatible with Apache Thrift. You can use ThriftPy2 together with the
  official implementation servers and clients, such as an upstream server with
  a thriftpy2 client or vice-versa.

  Currently implemented protocols and transports:

  * binary protocol (Python and Cython)

  * compact protocol (Python and Cython)

  * JSON protocol

  * Apache JSON protocol compatible with the Apache Thrift distribution's JSON protocol.
    Simply do ``from thriftpy2.protocol import TApacheJSONProtocolFactory`` and pass
    this to the ``proto_factory`` argument where appropriate.

  * buffered transport (Python & Cython)

  * framed transport

  * HTTP server and client

  * asyncio support (Python 3.7 or later)

- Can directly load a thrift file as a module, the client code will be generated on
  the fly.

  For example, ``pingpong_thrift = thriftpy2.load("pingpong.thrift", module_name="pingpong_thrift")``
  will load `pingpong.thrift` as the `pingpong_thrift` module.

  Or, when the import hook is enabled by ``thriftpy2.install_import_hook()``, you can
  directly use ``import pingpong_thrift`` to import the `pingpong.thrift` file
  as a module. You may also use ``from pingpong_thrift import PingService`` to
  import a specific object from the thrift module.

- Easy RPC server/client setup.


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
