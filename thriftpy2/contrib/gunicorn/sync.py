from __future__ import annotations

import errno
import socket

from gunicorn import sock as gsock
from gunicorn.workers.sync import SyncWorker

from thriftpy2.protocol import TBinaryProtocolFactory
from thriftpy2.transport import (
    TBufferedTransportFactory,
    TSocket,
    TTransportException,
)

from .base import ThriftWorkerMixin


class ThriftSyncWorker(ThriftWorkerMixin, SyncWorker):
    """Serve one thrift connection at a time, like gunicorn's sync worker.

    The connection is kept open and requests are processed in sequence until
    the client closes it, no request arrives within ``--keep-alive`` seconds,
    or the worker is asked to exit. ``--max-requests`` counts thrift calls.
    """

    proto_factory = TBinaryProtocolFactory()
    trans_factory = TBufferedTransportFactory()

    def handle(self, listener, client, addr):
        if self.cfg.is_ssl:
            client = gsock.ssl_wrap_socket(client, self.cfg)
        client.settimeout(self.cfg.keepalive or None)

        tsock = TSocket()
        tsock.set_handle(client)
        itrans, otrans, iprot, oprot = self.make_protocols(tsock)
        try:
            while self.alive:
                self.processor.process(iprot, oprot)
                self.nr += 1
                if self.nr >= self.max_requests:
                    self.log.info("Autorestarting worker after current "
                                  "request.")
                    self.alive = False
                self.notify()
        except TTransportException as e:
            if e.type != TTransportException.END_OF_FILE:
                self.log.warning("Transport error from %s: %s", addr, e)
        except socket.timeout:
            self.log.debug("Closing idle connection from %s", addr)
        except OSError as e:
            if e.errno in (errno.ECONNRESET, errno.EPIPE, errno.ENOTCONN):
                self.log.debug("Connection from %s dropped: %s", addr, e)
            else:
                self.log.exception("Socket error from %s", addr)
        except Exception:
            self.log.exception("Error processing request from %s", addr)
        finally:
            itrans.close()
            otrans.close()
