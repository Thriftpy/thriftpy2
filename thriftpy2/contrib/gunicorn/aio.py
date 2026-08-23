from __future__ import annotations

import asyncio
import errno
import os
import signal
import sys

from gunicorn import sock as gsock
from gunicorn.workers import base

from thriftpy2.contrib.aio.protocol.binary import TAsyncBinaryProtocolFactory
from thriftpy2.contrib.aio.socket import StreamHandler
from thriftpy2.contrib.aio.transport.buffered import (
    TAsyncBufferedTransportFactory,
)
from thriftpy2.transport import TTransportException

from .base import ThriftWorkerMixin


class _ClientStream(StreamHandler):
    """StreamHandler whose first read of each message honours an idle timeout.

    The worker marks the stream idle between requests. The read that starts
    the next message is bounded by the timeout while reads inside a message
    are not, so a slow request is never cut short by the keepalive setting.
    """

    def __init__(self, reader, writer, idle_timeout):
        super().__init__(reader, writer)
        self.idle_timeout = idle_timeout
        self.idle = True

    async def read(self, sz):
        if self.idle and self.idle_timeout:
            buff = await asyncio.wait_for(super().read(sz), self.idle_timeout)
        else:
            buff = await super().read(sz)
        self.idle = False
        return buff


class ThriftAsyncWorker(ThriftWorkerMixin, base.Worker):
    """Serve a ``TAsyncProcessor`` on an asyncio event loop.

    Each connection runs as a task, so one worker handles up to
    ``--worker-connections`` clients concurrently. Connections are closed
    after ``--keep-alive`` seconds without a request, and ``--max-requests``
    counts thrift calls across all connections.
    """

    proto_factory = TAsyncBinaryProtocolFactory()
    trans_factory = TAsyncBufferedTransportFactory()

    loop: asyncio.AbstractEventLoop

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # the loop is created in init_process, after the fork
        self.servers: list[asyncio.AbstractServer] = []
        self.connections: dict[asyncio.Task, _ClientStream] = {}
        self.quick_shutdown = False

    @classmethod
    def check_config(cls, cfg, log):
        if cfg.threads > 1:
            log.warning("ThriftAsyncWorker does not use the threads "
                        "setting, use worker_connections instead.")

    def init_process(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        super().init_process()

    def init_signals(self):
        for s in self.SIGNALS:
            signal.signal(s, signal.SIG_DFL)
        self.loop.add_signal_handler(signal.SIGQUIT, self.handle_quit_signal)
        self.loop.add_signal_handler(signal.SIGINT, self.handle_quit_signal)
        self.loop.add_signal_handler(signal.SIGTERM, self.handle_exit_signal)
        self.loop.add_signal_handler(signal.SIGUSR1, self.log.reopen_files)
        self.loop.add_signal_handler(signal.SIGABRT, self.handle_abort_signal)
        self.loop.add_signal_handler(
            signal.SIGWINCH, lambda: self.log.debug("worker: SIGWINCH ignored."))

    def handle_quit_signal(self):
        self.quick_shutdown = True
        if self.alive:
            self.alive = False
            self.cfg.worker_int(self)

    def handle_exit_signal(self):
        self.alive = False

    def handle_abort_signal(self):
        self.alive = False
        self.cfg.worker_abort(self)
        sys.exit(1)

    def run(self):
        try:
            self.loop.run_until_complete(self.serve())
        except Exception:
            self.log.exception("Worker exception")
        finally:
            self.cleanup()

    async def serve(self):
        ssl_context = gsock.ssl_context(self.cfg) if self.cfg.is_ssl else None
        for s in self.sockets:
            server = await asyncio.start_server(
                self.handle, sock=getattr(s, "sock", s), ssl=ssl_context)
            self.servers.append(server)

        while self.alive:
            self.notify()
            if self.ppid != os.getppid():
                self.log.info("Parent changed, shutting down: %s", self)
                break
            await asyncio.sleep(1.0)

        await self.shutdown()

    async def handle(self, reader, writer):
        addr = writer.get_extra_info("peername")
        if len(self.connections) >= self.cfg.worker_connections:
            self.log.warning("Connection limit reached, dropping %s", addr)
            writer.close()
            return
        task = asyncio.current_task()
        assert task is not None
        client = _ClientStream(reader, writer, self.cfg.keepalive or None)
        self.connections[task] = client
        itrans, otrans, iprot, oprot = self.make_protocols(client)
        try:
            while self.alive:
                client.idle = True
                await self.processor.process(iprot, oprot)
                self.nr += 1
                if self.nr >= self.max_requests:
                    self.log.info("Autorestarting worker after current "
                                  "request.")
                    self.alive = False
        except TTransportException as e:
            if e.type != TTransportException.END_OF_FILE:
                self.log.warning("Transport error from %s: %s", addr, e)
        except asyncio.TimeoutError:
            self.log.debug("Closing idle connection from %s", addr)
        except asyncio.CancelledError:
            pass
        except (ConnectionError, OSError) as e:
            if e.errno in (errno.ECONNRESET, errno.EPIPE, errno.ENOTCONN) \
                    or isinstance(e, ConnectionError):
                self.log.debug("Connection from %s dropped: %s", addr, e)
            else:
                self.log.exception("Socket error from %s", addr)
        except Exception:
            self.log.exception("Error processing request from %s", addr)
        finally:
            self.connections.pop(task, None)
            itrans.close()
            otrans.close()

    async def shutdown(self):
        for server in self.servers:
            server.close()

        # idle connections are closed right away, connections with a
        # request in flight get graceful_timeout to finish it
        if self.connections and not self.quick_shutdown:
            self.log.info("Waiting for %d connections to finish...",
                          len(self.connections))
            deadline = self.loop.time() + self.cfg.graceful_timeout
            while self.connections and self.loop.time() < deadline:
                if self.quick_shutdown:
                    break
                for task, client in list(self.connections.items()):
                    if client.idle:
                        task.cancel()
                await asyncio.sleep(0.1)

        for task in list(self.connections):
            task.cancel()
        if self.connections:
            await asyncio.gather(*self.connections, return_exceptions=True)

    def cleanup(self):
        try:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True))
            self.loop.close()
        except Exception as e:
            self.log.debug("Cleanup error: %s", e)
