#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import platform
import toml

from os.path import join, dirname
from setuptools import setup, find_packages, Extension


meta = toml.load(join(dirname(__file__), 'pyproject.toml') )
install_requires = meta["project"]["dependencies"]
dev_requires = meta["project"]["optional-dependencies"]["dev"]
tornado_requires = meta["project"]["optional-dependencies"]["tornado"]

try:
    from tornado import version as tornado_version
    if tornado_version < '5.0':
        tornado_requires.append("toro>=0.6")
        dev_requires.append("toro>=0.6")
except ImportError:
    # tornado will now only get installed and we'll get the newer one
    pass

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
      long_description=open("README.rst").read(),
      install_requires=install_requires,
      extras_require={
          "dev": dev_requires,
          "tornado": tornado_requires
      },
      ext_modules=ext_modules,
      include_package_data=True,
)
