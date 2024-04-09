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
CYTHON = not PYPY  # Cython always disabled in pypy
