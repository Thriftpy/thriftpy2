from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from thriftpy2.thrift import TPayload
    from ..transport.base import TAsyncTransportBase


class TAsyncProtocolFactory(Protocol):
    """Async protocol factory interface for type annotations."""

    def get_protocol(self, trans: TAsyncTransportBase) -> TAsyncProtocolBase:
        """Return an async protocol instance for the given transport."""
        ...


class TAsyncProtocolBase:
    """Base class for Thrift async protocol layer."""

    def __init__(self, trans: TAsyncTransportBase) -> None:
        self.trans = trans  # transport is public and used by TAsyncClient

    async def skip(self, ttype: int) -> None:
        raise NotImplementedError

    async def read_message_begin(self) -> tuple[str, int, int]:
        raise NotImplementedError

    async def read_message_end(self) -> None:
        raise NotImplementedError

    def write_message_begin(self, name: str, ttype: int, seqid: int) -> None:
        raise NotImplementedError

    def write_message_end(self) -> None:
        raise NotImplementedError

    async def read_struct(self, obj: TPayload) -> Any:
        raise NotImplementedError

    def write_struct(self, obj: TPayload) -> None:
        raise NotImplementedError
