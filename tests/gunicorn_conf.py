"""Gunicorn config file used by test_gunicorn.py.

Shows how to pick a protocol and transport by subclassing a worker right in
the config file and assigning it to worker_class.
"""
from thriftpy2.contrib.gunicorn import ThriftSyncWorker
from thriftpy2.protocol import TCompactProtocolFactory
from thriftpy2.transport import TFramedTransportFactory


class CompactFramedWorker(ThriftSyncWorker):
    proto_factory = TCompactProtocolFactory()
    trans_factory = TFramedTransportFactory()


worker_class = CompactFramedWorker
