"""
    thriftpy2._compat
    ~~~~~~~~~~~~~~~~~

    Interpreter feature detection.
"""

import platform
import sys

PYPY = "__pypy__" in sys.modules

UNIX = platform.system() in ("Linux", "Darwin")
CYTHON = not PYPY  # Cython always disabled in pypy
