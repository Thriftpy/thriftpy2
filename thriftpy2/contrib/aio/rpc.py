# -*- coding: utf-8 -*-
import socket
import urllib
import warnings

from .client import TAsyncClient
from .processor import TAsyncProcessor
from .protocol.binary import TAsyncBinaryProtocolFactory
from .server import TAsyncServer
from .socket import TAsyncServerSocket, TAsyncSocket
from .transport.buffered import TAsyncBufferedTransportFactory


async def make_client(service, host='localhost', port=9090, unix_socket=None,
                      proto_factory=TAsyncBinaryProtocolFactory(),
                      trans_factory=TAsyncBufferedTransportFactory(),
                      timeout=3000, connect_timeout=None,
                      cafile=None, ssl_context=None,
                      certfile=None, keyfile=None,
                      validate=True, url='',
                      socket_timeout=None, socket_family=socket.AF_INET):
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


def make_server(service, handler,
                host="localhost", port=9090, unix_socket=None,
                proto_factory=TAsyncBinaryProtocolFactory(),
                trans_factory=TAsyncBufferedTransportFactory(),
                client_timeout=3000, certfile=None,
                keyfile=None, ssl_context=None, loop=None,
                socket_family=socket.AF_INET):
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
