from __future__ import annotations

import importlib
import os
from typing import Any

from gunicorn.errors import AppImportError


def import_processor(uri: str) -> Any:
    """Import ``module:obj`` without gunicorn's callable requirement."""
    module, sep, name = uri.partition(":")
    if not sep:
        name = "app"
    try:
        mod = importlib.import_module(module)
    except ImportError:
        if module.endswith(".py") and os.path.exists(module):
            raise ImportError(
                "Failed to find application, did you mean '%s:%s'?"
                % (module.rsplit(".", 1)[0], name))
        raise
    try:
        return getattr(mod, name)
    except AttributeError:
        raise AppImportError(
            "Failed to find attribute %r in %r." % (name, module))


def resolve_processor(obj: Any) -> Any:
    """Accept a processor, or a zero argument factory returning one."""
    if obj is None:
        raise AppImportError("Failed to find thrift processor.")
    if not hasattr(obj, "process") and callable(obj):
        obj = obj()
    if not hasattr(obj, "process"):
        raise AppImportError(
            "Application object must be a thrift processor or a callable "
            "returning one, got %r." % (obj,))
    return obj


class ThriftWorkerMixin:
    """Shared processor loading for the thrift workers."""

    proto_factory: Any = None
    trans_factory: Any = None

    def load_wsgi(self) -> None:
        app = self.app  # type: ignore[attr-defined]
        # Gunicorn's own loader rejects non callable objects, so when the
        # application has not been loaded yet (no --preload) import the
        # object ourselves. Custom Application subclasses without app_uri
        # fall back to the regular wsgi() path.
        if getattr(app, "callable", None) is None and \
                getattr(app, "app_uri", None):
            obj = import_processor(app.app_uri)
        else:
            obj = app.wsgi()
        self.processor = resolve_processor(obj)

    def make_protocols(self, client: Any) -> tuple[Any, Any, Any, Any]:
        itrans = self.trans_factory.get_transport(client)
        iprot = self.proto_factory.get_protocol(itrans)
        if getattr(self.proto_factory, "shared_instance", False):
            return itrans, itrans, iprot, iprot
        otrans = self.trans_factory.get_transport(client)
        oprot = self.proto_factory.get_protocol(otrans)
        return itrans, otrans, iprot, oprot
