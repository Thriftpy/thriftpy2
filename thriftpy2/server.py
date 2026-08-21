from __future__ import annotations

import logging
import threading

from thriftpy2.protocol import TBinaryProtocolFactory, THeaderProtocolFactory
from thriftpy2.protocol.base import TProtocolBase, TProtocolFactory
from thriftpy2.thrift import TProcessor
from thriftpy2.transport import (
    TBufferedTransportFactory,
    TServerSocket,
    TTransportException,
)
from thriftpy2.transport.base import TTransportBase, TTransportFactory


logger = logging.getLogger(__name__)


class TServer:
    def __init__(self, processor: TProcessor, trans: TServerSocket,
                 itrans_factory: TTransportFactory | None = None,
                 iprot_factory: TProtocolFactory | None = None,
                 otrans_factory: TTransportFactory | None = None,
                 oprot_factory: TProtocolFactory | None = None) -> None:
        self.processor = processor
        self.trans = trans

        self.itrans_factory = itrans_factory or TBufferedTransportFactory()
        self.iprot_factory = iprot_factory or TBinaryProtocolFactory()
        self.otrans_factory = otrans_factory or self.itrans_factory
        self.oprot_factory = oprot_factory or self.iprot_factory

        input_is_header = isinstance(self.iprot_factory,
                                     THeaderProtocolFactory)
        output_is_header = isinstance(self.oprot_factory,
                                      THeaderProtocolFactory)
        if input_is_header != output_is_header:
            raise ValueError("THeaderProtocol servers require that both the "
                             "input and output protocols are THeaderProtocol.")

    def _make_protocols(self, client: TTransportBase) -> tuple[
            TTransportBase, TTransportBase, TProtocolBase, TProtocolBase]:
        itrans = self.itrans_factory.get_transport(client)
        iprot = self.iprot_factory.get_protocol(itrans)
        if isinstance(self.iprot_factory, THeaderProtocolFactory):
            # THeaderProtocol detects the client dialect while reading and
            # must answer with the same one, so a single protocol instance
            # has to serve both directions
            return itrans, itrans, iprot, iprot
        otrans = self.otrans_factory.get_transport(client)
        oprot = self.oprot_factory.get_protocol(otrans)
        return itrans, otrans, iprot, oprot

    def serve(self) -> None:
        pass

    def close(self) -> None:
        pass


class TSimpleServer(TServer):
    """Simple single-threaded server that just pumps around one transport."""

    def __init__(self, *args, **kwargs) -> None:
        TServer.__init__(self, *args, **kwargs)
        self.closed = False

    def serve(self) -> None:
        self.trans.listen()
        while not self.closed:
            client = self.trans.accept()
            itrans, otrans, iprot, oprot = self._make_protocols(client)
            try:
                while not self.closed:
                    self.processor.process(iprot, oprot)
            except TTransportException:
                pass
            except Exception as x:
                logger.exception(x)

            itrans.close()
            otrans.close()

    def close(self) -> None:
        self.closed = True


class TThreadedServer(TServer):
    """Threaded server that spawns a new thread per each connection."""

    def __init__(self, *args, **kwargs) -> None:
        self.daemon = kwargs.pop("daemon", False)
        TServer.__init__(self, *args, **kwargs)
        self.closed = False

    def serve(self) -> None:
        self.trans.listen()
        while not self.closed:
            try:
                client = self.trans.accept()
                t = threading.Thread(target=self.handle, args=(client,))
                t.daemon = self.daemon
                t.start()
            except KeyboardInterrupt:
                raise
            except Exception as x:
                logger.exception(x)

    def handle(self, client: TTransportBase) -> None:
        itrans, otrans, iprot, oprot = self._make_protocols(client)
        try:
            while True:
                self.processor.process(iprot, oprot)
        except TTransportException:
            pass
        except Exception as x:
            logger.exception(x)

        itrans.close()
        otrans.close()

    def close(self) -> None:
        self.closed = True
