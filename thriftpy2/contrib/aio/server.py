import asyncio
import logging
from typing import Optional

from thriftpy2.transport import TTransportException

from .protocol.binary import TAsyncBinaryProtocolFactory
from .transport.buffered import TAsyncBufferedTransportFactory

logger = logging.getLogger(__name__)


class TAsyncServer:

    def __init__(self, processor, trans,
                 itrans_factory=None, iprot_factory=None,
                 otrans_factory=None, oprot_factory=None,
                 loop: Optional[asyncio.AbstractEventLoop] = None):
        self.processor = processor
        self.trans = trans

        self.itrans_factory = itrans_factory or TAsyncBufferedTransportFactory()
        self.iprot_factory = iprot_factory or TAsyncBinaryProtocolFactory()
        self.otrans_factory = otrans_factory or self.itrans_factory
        self.oprot_factory = oprot_factory or self.iprot_factory

        self.loop: Optional[asyncio.AbstractEventLoop] = loop
        self.closed = False
        self.server = None

    def serve(self):
        self.init_server()
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.close())

    def init_server(self):
        self.trans.listen()
        if not self.loop:
            import warnings
            warnings.warn(
                "No event loop provided. Creating a new event loop automatically. "
                "It is recommended to explicitly pass a loop parameter for better control. "
                "Example: loop = asyncio.new_event_loop(); make_server(..., loop=loop)",
                DeprecationWarning,
                stacklevel=3
            )
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        self.server = self.loop.run_until_complete(
            self.trans.accept(self.handle)
        )

    async def handle(self, client):
        itrans = self.itrans_factory.get_transport(client)
        otrans = self.otrans_factory.get_transport(client)
        iprot = self.iprot_factory.get_protocol(itrans)
        oprot = self.oprot_factory.get_protocol(otrans)
        try:
            while not client.reader.at_eof():
                await self.processor.process(iprot, oprot)
        except TTransportException:
            pass
        except Exception as x:
            logger.exception(x)

        itrans.close()

    async def close(self):
        if self.closed:
            return
        self.server.close()
        await self.server.wait_closed()
        self.closed = True
        self.server = None
