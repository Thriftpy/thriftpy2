# -*- coding: utf-8 -*-

"""
    thriftpy2._compat
    ~~~~~~~~~~~~~

    py2/py3 compatibility support.
"""

from __future__ import absolute_import

import platform
import sys

PYPY = "__pypy__" in sys.modules

UNIX = platform.system() in ("Linux", "Darwin")
CYTHON = UNIX and not PYPY  # Cython always disabled in pypy and windows


def with_metaclass(meta, *bases):
    """Create a base class with a metaclass for py2 & py3

    This code snippet is copied from six."""
    # This requires a bit of explanation: the basic idea is to make a
    # dummy metaclass for one level of class instantiation that replaces
    # itself with the actual metaclass.  Because of internal type checks
    # we also need to make sure that we downgrade the custom metaclass
    # for one level to something closer to type (that's why __call__ and
    # __init__ comes back from type etc.).
    class metaclass(meta):
        __call__ = type.__call__
        __init__ = type.__init__

        def __new__(cls, name, this_bases, d):
            if this_bases is None:
                return type.__new__(cls, name, (), d)
            return meta(name, bases, d)
    return metaclass('temporary_class', None, {})
