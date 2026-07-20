from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Tuple

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol

if TYPE_CHECKING:
    from ..thrift import TPayload
    from ..transport.base import TTransportBase


class TProtocolFactory(Protocol):
    """Protocol factory interface for type annotations."""

    def get_protocol(self, trans: TTransportBase) -> TProtocolBase:
        """Return a protocol instance for the given transport."""
        ...


class TProtocolBase(object):
    """Base class for Thrift protocol layer."""

    def __init__(self, trans: TTransportBase) -> None:
        self.trans = trans  # transport is public and used by TClient

    def skip(self, ttype: int) -> None:
        raise NotImplementedError

    def read_message_begin(self) -> Tuple[str, int, int]:
        raise NotImplementedError

    def read_message_end(self) -> None:
        raise NotImplementedError

    def write_message_begin(self, name: str, ttype: int, seqid: int) -> None:
        raise NotImplementedError

    def write_message_end(self) -> None:
        raise NotImplementedError

    def read_struct(self, obj: TPayload) -> Any:
        raise NotImplementedError

    def write_struct(self, obj: TPayload) -> None:
        raise NotImplementedError
