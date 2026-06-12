"""
    thriftpy2._compat
    ~~~~~~~~~~~~~

    py2/py3 compatibility support.
"""

import platform
import sys

PYPY = "__pypy__" in sys.modules

UNIX = platform.system() in ("Linux", "Darwin")
CYTHON = not PYPY  # Cython always disabled in pypy
