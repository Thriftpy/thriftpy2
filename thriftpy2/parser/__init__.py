"""
    thriftpy2.parser
    ~~~~~~~~~~~~~~~

    Thrift parser using ply
"""

from __future__ import annotations

import os
import sys
import types
from typing import List, Optional, TextIO, Union

from .parser import parse, parse_fp
from .exc import ThriftModuleNameConflict
from .exc import ThriftParserError  # noqa: F401, re-exported for compat


def load(
    path: Union[str, os.PathLike],
    module_name: Optional[str] = None,
    include_dirs: Optional[List[Union[str, os.PathLike]]] = None,
    include_dir: Optional[Union[str, os.PathLike]] = None,
    encoding: str = 'utf-8',
) -> types.ModuleType:
    """Load thrift file as a module.

    The module loaded and objects inside may only be pickled if module_name
    was provided.

    Note: `include_dir` will be depreacated in the future, use `include_dirs`
    instead. If `include_dir` was provided (not None), it will be appended to
    `include_dirs`.
    """
    path = os.fspath(path)
    if include_dirs is not None:
        include_dirs = [os.fspath(d) for d in include_dirs]
    if include_dir is not None:
        include_dir = os.fspath(include_dir)
    real_module = bool(module_name)
    # `parse` resolves forward references and caches a fully-built module.
    thrift = parse(path, module_name, include_dirs=include_dirs,
                   include_dir=include_dir, encoding=encoding)

    # add sub modules to sys.modules recursively
    if real_module:
        sys.modules[module_name] = thrift
        include_thrifts = thrift.__thrift_meta__["includes"][:]
        while include_thrifts:
            include_thrift = include_thrifts.pop()
            registered_thrift = sys.modules.get(include_thrift.__thrift_module_name__)
            if registered_thrift is None:
                sys.modules[include_thrift.__thrift_module_name__] = include_thrift
                if hasattr(include_thrift, "__thrift_meta__"):
                    include_thrifts.extend(
                        include_thrift.__thrift_meta__["includes"][:])
            else:
                if registered_thrift.__thrift_file__ != include_thrift.__thrift_file__:
                    raise ThriftModuleNameConflict(
                        'Module name conflict between "%s" and "%s"' %
                        (registered_thrift.__thrift_file__, include_thrift.__thrift_file__)
                    )
    return thrift


def load_fp(source: TextIO, module_name: str) -> types.ModuleType:
    """Load thrift file like object as a module.
    """
    thrift = parse_fp(source, module_name)
    sys.modules[module_name] = thrift
    return thrift


def _import_module(import_name):
    if '.' in import_name:
        module, obj = import_name.rsplit('.', 1)
        return getattr(__import__(module, None, None, [obj]), obj)
    else:
        return __import__(import_name)


def load_module(fullname: str) -> types.ModuleType:
    """Load thrift_file by fullname, fullname should have '_thrift' as
    suffix.
    The loader will replace the '_thrift' with '.thrift' and use it as
    filename to locate the real thrift file.
    """
    if not fullname.endswith("_thrift"):
        raise ImportError(
            "thriftpy2 can only load module with '_thrift' suffix")

    if fullname in sys.modules:
        return sys.modules[fullname]

    if '.' in fullname:
        module_name, thrift_module_name = fullname.rsplit('.', 1)
        module = _import_module(module_name)
        path_prefix = os.path.dirname(os.path.abspath(module.__file__))
        path = os.path.join(path_prefix, thrift_module_name)
    else:
        path = fullname
    thrift_file = "{}.thrift".format(path[:-7])

    module = load(thrift_file, module_name=fullname)
    sys.modules[fullname] = module
    return sys.modules[fullname]
