"""
Async HTTP transport for thriftpy2.

# Run server:
>>> import asyncio
>>> import thriftpy2
>>> from thriftpy2.contrib.aio.http import make_server
>>> pingpong = thriftpy2.load("pingpong.thrift")
>>>
>>> class Dispatcher:
>>>     async def ping(self):
>>>         return "pong"
>>>
>>> server = make_server(pingpong.PingService, Dispatcher(),
                         host='127.0.0.1', port=6000)
>>> asyncio.run(server.serve())

# Run client:
>>> import asyncio
>>> import thriftpy2
>>> from thriftpy2.contrib.aio.http import make_client
>>> pingpong = thriftpy2.load("pingpong.thrift")
>>> async def main():
...     client = await make_client(pingpong.PingService,
...                                host='127.0.0.1', port=6000)
...     print(await client.ping())
...     client.close()
>>> asyncio.run(main())
"""

import asyncio
import urllib.parse
from contextlib import asynccontextmanager
from io import BytesIO

import aiohttp
from aiohttp import web

from thriftpy2.contrib.aio.client import TAsyncClient
from thriftpy2.contrib.aio.processor import TAsyncProcessor
from thriftpy2.contrib.aio.protocol import TAsyncBinaryProtocolFactory
from thriftpy2.contrib.aio.transport.base import TAsyncTransportBase
from thriftpy2.transport import TTransportException

HTTP_URI = '{scheme}://{host}:{port}{path}'
DEFAULT_HTTP_CLIENT_TIMEOUT_MS = 30000  # 30 seconds


class TAsyncHttpHeaderFactory:
    """Default header factory that returns custom headers."""

    def __init__(self, headers=None):
        """Initialize a header factory.

        @param headers(dict): A dictionary of static headers the factory generates
        """
        self._headers = headers if headers else {}

    def get_headers(self):
        return self._headers


class TAsyncMemoryBuffer(TAsyncTransportBase):
    """Async memory buffer transport."""

    def __init__(self, value=b''):
        self._buffer = BytesIO(value)

    def is_open(self):
        return True

    async def open(self):
        pass

    def close(self):
        self._buffer.close()

    async def _read(self, sz):
        return self._buffer.read(sz)

    def write(self, buf):
        self._buffer.write(buf)

    async def flush(self):
        pass

    def getvalue(self):
        return self._buffer.getvalue()

    def setvalue(self, value):
        self._buffer = BytesIO(value)


class TAsyncHttpClient(TAsyncTransportBase):
    """Async HTTP implementation of TTransport."""

    def __init__(self, uri, timeout=None, ssl_context=None,
                 http_header_factory=None):
        """Initialize an async HTTP transport.

        @param uri(str): The http_scheme://host:port/path to connect to.
        @param timeout: Timeout in milliseconds.
        @param ssl_context: SSL context for HTTPS connections.
        @param http_header_factory: Factory for custom HTTP headers.
        """
        parsed = urllib.parse.urlparse(uri)
        self.scheme = parsed.scheme
        assert self.scheme in ('http', 'https')

        if self.scheme == 'http':
            self.port = parsed.port or 80
        elif self.scheme == 'https':
            self.port = parsed.port or 443

        self.host = parsed.hostname
        self.path = parsed.path or '/'
        if parsed.query:
            self.path += '?%s' % parsed.query

        self._wbuf = BytesIO()
        self._rbuf = BytesIO()
        self._session = None
        self._http_header_factory = http_header_factory or TAsyncHttpHeaderFactory()
        self._timeout = None
        self._ssl_context = ssl_context
        if timeout:
            self.set_timeout(timeout)

    def is_open(self):
        return self._session is not None and not self._session.closed

    async def open(self):
        if self._session is not None and not self._session.closed:
            return

        timeout = aiohttp.ClientTimeout(
            total=self._timeout
        ) if self._timeout else None

        connector = aiohttp.TCPConnector(ssl=self._ssl_context)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )

    def close(self):
        """Synchronous close - marks session as closed.

        For proper async cleanup, use aclose() instead.
        """
        if self._session is not None:
            # Just mark as None, the session will be cleaned up by GC
            # For proper cleanup, use aclose() or client_context
            self._session = None

    async def aclose(self):
        """Async close method."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    def set_timeout(self, ms):
        """Set timeout in milliseconds."""
        self._timeout = ms / 1000.0 if (ms and ms > 0) else None

    def set_custom_headers(self, headers):
        self._http_header_factory = TAsyncHttpHeaderFactory(headers)

    async def _read(self, sz):
        return self._rbuf.read(sz)

    def write(self, buf):
        self._wbuf.write(buf)

    async def flush(self):
        """Send buffered data as HTTP POST request."""
        data = self._wbuf.getvalue()
        self._wbuf = BytesIO()

        if not data:
            return

        if not self.is_open():
            await self.open()

        url = HTTP_URI.format(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=self.path
        )

        headers = {
            'Content-Type': 'application/x-thrift',
            'Accept': 'application/x-thrift',
        }

        custom_headers = self._http_header_factory.get_headers()
        if custom_headers:
            headers.update(custom_headers)

        if 'User-Agent' not in headers:
            headers['User-Agent'] = 'Python/TAsyncHttpClient'

        async with self._session.post(url, data=data, headers=headers) as resp:
            self.code = resp.status
            self.message = resp.reason
            self.headers = resp.headers

            if resp.status != 200:
                raise TTransportException(
                    type=TTransportException.UNKNOWN,
                    message='HTTP request failed with status %d: %s' % (
                        resp.status, resp.reason
                    )
                )

            response_data = await resp.read()
            self._rbuf = BytesIO(response_data)


class TAsyncHttpServer:
    """Async HTTP server based on aiohttp.web."""

    def __init__(self, processor, host, port, iprot_factory,
                 ssl_context=None):
        """Initialize the async HTTP server.

        @param processor: The TAsyncProcessor to handle requests.
        @param host: The host to bind to.
        @param port: The port to bind to.
        @param iprot_factory: The protocol factory for incoming requests.
        @param ssl_context: SSL context for HTTPS.
        """
        self.processor = processor
        self.host = host
        self.port = port
        self.iprot_factory = iprot_factory
        self.ssl_context = ssl_context
        self._app = None
        self._runner = None
        self._site = None

    async def _handle_request(self, request):
        """Handle incoming HTTP POST request."""
        if request.method != 'POST':
            return web.Response(status=405, text='Method Not Allowed')

        try:
            data = await request.read()

            # Create input transport and protocol
            itrans = TAsyncMemoryBuffer(data)
            iprot = self.iprot_factory.get_protocol(itrans)

            # Create output transport and protocol
            otrans = TAsyncMemoryBuffer()
            oprot = self.iprot_factory.get_protocol(otrans)

            # Process the request
            await self.processor.process(iprot, oprot)

            # Return response
            response_data = otrans.getvalue()
            return web.Response(
                body=response_data,
                content_type='application/x-thrift'
            )

        except Exception as e:
            return web.Response(
                status=500,
                text='Internal Server Error: %s' % str(e)
            )

    async def serve(self):
        """Start the HTTP server."""
        self._app = web.Application()
        self._app.router.add_post('/{path:.*}', self._handle_request)
        self._app.router.add_post('', self._handle_request)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(
            self._runner,
            self.host,
            self.port,
            ssl_context=self.ssl_context
        )
        await self._site.start()

        # Keep running until closed
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    async def close(self):
        """Close the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            self._app = None


async def make_client(service, host='localhost', port=9090, path='',
                      scheme='http', proto_factory=None,
                      ssl_context=None, http_header_factory=None,
                      timeout=DEFAULT_HTTP_CLIENT_TIMEOUT_MS, url=''):
    """Create an async HTTP client.

    @param service: The Thrift service class.
    @param host: The host to connect to.
    @param port: The port to connect to.
    @param path: The URL path.
    @param scheme: The URL scheme (http or https).
    @param proto_factory: The protocol factory.
    @param ssl_context: SSL context for HTTPS.
    @param http_header_factory: Factory for custom HTTP headers.
    @param timeout: Timeout in milliseconds.
    @param url: Full URL (overrides host, port, scheme, path).
    @return: TAsyncClient instance.
    """
    if proto_factory is None:
        proto_factory = TAsyncBinaryProtocolFactory()

    if url:
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.hostname or host
        port = parsed_url.port or port
        scheme = parsed_url.scheme or scheme
        path = parsed_url.path or path

    if path and path[0] != '/':
        path = '/' + path

    uri = HTTP_URI.format(scheme=scheme, host=host, port=port, path=path)
    http_client = TAsyncHttpClient(
        uri, timeout, ssl_context, http_header_factory
    )

    await http_client.open()
    iprot = proto_factory.get_protocol(http_client)

    return TAsyncClient(service, iprot)


@asynccontextmanager
async def client_context(service, host='localhost', port=9090, path='',
                         scheme='http', proto_factory=None,
                         ssl_context=None, http_header_factory=None,
                         timeout=DEFAULT_HTTP_CLIENT_TIMEOUT_MS, url=''):
    """Async context manager for HTTP client.

    @param service: The Thrift service class.
    @param host: The host to connect to.
    @param port: The port to connect to.
    @param path: The URL path.
    @param scheme: The URL scheme (http or https).
    @param proto_factory: The protocol factory.
    @param ssl_context: SSL context for HTTPS.
    @param http_header_factory: Factory for custom HTTP headers.
    @param timeout: Timeout in milliseconds.
    @param url: Full URL (overrides host, port, scheme, path).
    @return: TAsyncClient instance.
    """
    if proto_factory is None:
        proto_factory = TAsyncBinaryProtocolFactory()

    if url:
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.hostname or host
        port = parsed_url.port or port
        scheme = parsed_url.scheme or scheme
        path = parsed_url.path or path

    if path and path[0] != '/':
        path = '/' + path

    uri = HTTP_URI.format(scheme=scheme, host=host, port=port, path=path)
    http_client = TAsyncHttpClient(
        uri, timeout, ssl_context, http_header_factory
    )

    try:
        await http_client.open()
        iprot = proto_factory.get_protocol(http_client)
        yield TAsyncClient(service, iprot)
    finally:
        await http_client.aclose()


def make_server(service, handler, host, port,
                proto_factory=None, ssl_context=None):
    """Create an async HTTP server.

    @param service: The Thrift service class.
    @param handler: The handler implementing the service methods.
    @param host: The host to bind to.
    @param port: The port to bind to.
    @param proto_factory: The protocol factory.
    @param ssl_context: SSL context for HTTPS.
    @return: TAsyncHttpServer instance.
    """
    if proto_factory is None:
        proto_factory = TAsyncBinaryProtocolFactory()

    processor = TAsyncProcessor(service, handler)
    server = TAsyncHttpServer(
        processor, host, port,
        iprot_factory=proto_factory,
        ssl_context=ssl_context
    )
    return server
