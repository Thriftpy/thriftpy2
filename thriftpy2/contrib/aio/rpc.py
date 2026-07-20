import socket
import ssl
import types
import urllib
import warnings
from typing import Any, Optional

from thriftpy2.protocol.base import TProtocolFactory
from thriftpy2.transport.base import TTransportFactory

from .client import TAsyncClient
from .processor import TAsyncProcessor
from .protocol.binary import TAsyncBinaryProtocolFactory
from .server import TAsyncServer
from .socket import TAsyncServerSocket, TAsyncSocket
from .transport.buffered import TAsyncBufferedTransportFactory


async def make_client(
        service: types.ModuleType, host: str = 'localhost', port: int = 9090,
        unix_socket: Optional[str] = None,
        proto_factory: TProtocolFactory = TAsyncBinaryProtocolFactory(),
        trans_factory: TTransportFactory = TAsyncBufferedTransportFactory(),
        timeout: Optional[int] = 3000, connect_timeout: Optional[int] = None,
        cafile: Optional[str] = None, ssl_context: Optional[ssl.SSLContext] = None,
        certfile: Optional[str] = None, keyfile: Optional[str] = None,
        validate: bool = True, url: str = '', socket_timeout: Optional[int] = None,
        socket_family: socket.AddressFamily = socket.AF_INET) -> TAsyncClient:
    if socket_timeout is not None:
        warnings.warn(
            "The 'socket_timeout' argument is deprecated. "
            "Please use 'timeout' instead.",
            DeprecationWarning,
        )
        timeout = socket_timeout
    if url:
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.hostname or host
        port = parsed_url.port or port
    if unix_socket:
        client_socket = TAsyncSocket(
            unix_socket=unix_socket,
            connect_timeout=connect_timeout,
            socket_timeout=timeout,
        )
        if certfile:
            warnings.warn("SSL only works with host:port, not unix_socket.")
    elif host and port:
        client_socket = TAsyncSocket(
            host,
            port,
            socket_timeout=timeout,
            connect_timeout=connect_timeout,
            cafile=cafile,
            ssl_context=ssl_context,
            certfile=certfile,
            keyfile=keyfile,
            validate=validate,
            socket_family=socket_family,
        )
    else:
        raise ValueError("Either host/port or unix_socket"
                         " or url must be provided.")

    transport = trans_factory.get_transport(client_socket)
    protocol = proto_factory.get_protocol(transport)
    await transport.open()
    return TAsyncClient(service, protocol)


def make_server(
        service: types.ModuleType, handler: Any, host: str = 'localhost',
        port: int = 9090, unix_socket: Optional[str] = None,
        proto_factory: TProtocolFactory = TAsyncBinaryProtocolFactory(),
        trans_factory: TTransportFactory = TAsyncBufferedTransportFactory(),
        client_timeout: Optional[int] = 3000, certfile: Optional[str] = None,
        keyfile: Optional[str] = None, ssl_context: Optional[ssl.SSLContext] = None,
        loop: Optional[Any] = None,
        socket_family: socket.AddressFamily = socket.AF_INET) -> TAsyncServer:
    processor = TAsyncProcessor(service, handler)

    if unix_socket:
        server_socket = TAsyncServerSocket(unix_socket=unix_socket)
        if certfile:
            warnings.warn("SSL only works with host:port, not unix_socket.")
    elif host and port:
        server_socket = TAsyncServerSocket(
            host=host,
            port=port,
            client_timeout=client_timeout,
            certfile=certfile,
            keyfile=keyfile,
            ssl_context=ssl_context,
            socket_family=socket_family,
        )
    else:
        raise ValueError("Either host/port or unix_socket must be provided.")

    server = TAsyncServer(processor, server_socket,
                          iprot_factory=proto_factory,
                          itrans_factory=trans_factory, loop=loop)
    return server
