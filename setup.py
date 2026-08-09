#!/usr/bin/env python

import sys
import platform

from setuptools import setup, find_packages, Extension


ext_modules = []

# pypy detection
PYPY = "__pypy__" in sys.modules
UNIX = platform.system() in ("Linux", "Darwin")
WINDOWS = platform.system() == "Windows"

# only build ext in CPython
if not PYPY:
    from Cython.Build import cythonize
    cythonize("thriftpy2/transport/cybase.pyx")
    cythonize("thriftpy2/transport/**/*.pyx")
    cythonize("thriftpy2/protocol/cybin/cybin.pyx")

    libraries = []
    if WINDOWS:
        libraries.append("Ws2_32")

    ext_modules.append(Extension("thriftpy2.transport.cybase",
                                 ["thriftpy2/transport/cybase.c"]))
    ext_modules.append(Extension("thriftpy2.transport.buffered.cybuffered",
                                 ["thriftpy2/transport/buffered/cybuffered.c"]))
    ext_modules.append(Extension("thriftpy2.transport.memory.cymemory",
                                 ["thriftpy2/transport/memory/cymemory.c"]))
    ext_modules.append(Extension("thriftpy2.transport.framed.cyframed",
                                 ["thriftpy2/transport/framed/cyframed.c"],
                                 libraries=libraries))
    ext_modules.append(Extension("thriftpy2.transport.sasl.cysasl",
                                 ["thriftpy2/transport/sasl/cysasl.c"]))
    ext_modules.append(Extension("thriftpy2.protocol.cybin.cybin",
                                 ["thriftpy2/protocol/cybin/cybin.c"],
                                 libraries=libraries))

setup(
      packages=find_packages(exclude=['benchmark', 'docs', 'tests']),
      zip_safe=False,
      ext_modules=ext_modules,
      include_package_data=True,
      package_data={"thriftpy2": ["py.typed"]},
)
