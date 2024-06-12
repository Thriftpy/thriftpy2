# -*- coding: utf-8 -*-

from __future__ import absolute_import

import importlib.abc
import importlib.util
import sys

from .parser import load_module


# TODO: The load process does not compatible with Python standard, e.g., if the
# specified thrift file does not exists, it raises FileNotFoundError, and skipped
# the other meta finders in the sys.meta_path.
class ThriftImporter(importlib.abc.MetaPathFinder):
    def __init__(self, extension="_thrift"):
        self.extension = extension

    def find_spec(self, fullname, path, target=None):
        if not fullname.endswith(self.extension):
            return None
        return importlib.util.spec_from_loader(fullname,
                                               ThriftLoader(fullname))


class ThriftLoader(importlib.abc.Loader):
    def __init__(self, fullname):
        self.fullname = fullname

    def create_module(self, spec):
        return load_module(self.fullname)

    def exec_module(self, module):
        pass


_imp = ThriftImporter()


def install_import_hook():
    global _imp
    sys.meta_path[:] = [x for x in sys.meta_path if _imp is not x] + [_imp]


def remove_import_hook():
    global _imp
    sys.meta_path[:] = [x for x in sys.meta_path if _imp is not x]
