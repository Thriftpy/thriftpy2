from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from thriftpy2.transport import TTransportException


async def readall(read_fn: Callable[[int], Awaitable[bytes]], sz: int) -> bytes:
    buff = b''
    have = 0
    while have < sz:
        chunk = await read_fn(sz - have)
        have += len(chunk)
        buff += chunk

        if len(chunk) == 0:
            raise TTransportException(
                TTransportException.END_OF_FILE,
                "End of file reading from transport",
            )

    return buff


class TAsyncTransportFactory(Protocol):
    """Async transport factory interface for type annotations."""

    def get_transport(self, trans: TAsyncTransportBase) -> TAsyncTransportBase:
        """Return an async transport instance wrapping the given transport."""
        ...


class TAsyncTransportBase:
    """Base class for Thrift async transport layer."""

    def is_open(self) -> bool:
        raise NotImplementedError

    async def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    async def _read(self, sz: int) -> bytes:
        raise NotImplementedError

    async def read(self, sz: int) -> bytes:
        return await readall(self._read, sz)

    def write(self, buf: bytes) -> None:
        raise NotImplementedError

    async def flush(self) -> None:
        raise NotImplementedError
