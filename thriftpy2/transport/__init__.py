# -*- coding: utf-8 -*-

from __future__ import absolute_import

from thriftpy2._compat import CYTHON

from .base import TTransportBase, TTransportException
from .socket import TSocket, TServerSocket
from .sslsocket import TSSLSocket, TSSLServerSocket
from ._ssl import create_thriftpy_context
from .buffered import TBufferedTransport, TBufferedTransportFactory
from .framed import TFramedTransport, TFramedTransportFactory
from .memory import TMemoryBuffer
from .sasl import TSaslClientTransport

if CYTHON:
    from .buffered import TCyBufferedTransport, TCyBufferedTransportFactory
    from .framed import TCyFramedTransport, TCyFramedTransportFactory
    from .memory import TCyMemoryBuffer
    from .sasl import TCySaslClientTransport

    # enable cython binary by default for CPython.
    TMemoryBuffer = TCyMemoryBuffer  # noqa
    TBufferedTransport = TCyBufferedTransport  # noqa
    TBufferedTransportFactory = TCyBufferedTransportFactory  # noqa
    TFramedTransport = TCyFramedTransport  # noqa
    TFramedTransportFactory = TCyFramedTransportFactory  # noqa
    TSaslClientTransport = TCySaslClientTransport  # noqa
else:
    # disable cython binary protocol for PYPY since it's slower.
    TCyMemoryBuffer = TMemoryBuffer
    TCyBufferedTransport = TBufferedTransport
    TCyBufferedTransportFactory = TBufferedTransportFactory
    TCyFramedTransport = TFramedTransport
    TCyFramedTransportFactory = TFramedTransportFactory
    TCySaslClientTransport = TSaslClientTransport

__all__ = [
    "TSocket", "TServerSocket",
    "TSSLSocket", "TSSLServerSocket", "create_thriftpy_context",
    "TTransportBase", "TTransportException",
    "TMemoryBuffer", "TFramedTransport", "TFramedTransportFactory",
    "TBufferedTransport", "TBufferedTransportFactory", "TCyMemoryBuffer",
    "TCyBufferedTransport", "TCyBufferedTransportFactory",
    "TCyFramedTransport", "TCyFramedTransportFactory",
    "TSaslClientTransport", "TCySaslClientTransport",
]
