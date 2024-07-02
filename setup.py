#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import platform

from setuptools import setup, find_packages, Extension


install_requires = [
    "ply>=3.4,<4.0",
    "six~=1.15",
]

tornado_requires = [
    "tornado>=4.0,<7.0; python_version>='3.12'",
    "tornado>=4.0,<6.0; python_version<'3.12'",
]

try:
    from tornado import version as tornado_version
    if tornado_version < '5.0':
        tornado_requires.append("toro>=0.6")
except ImportError:
    # tornado will now only get installed and we'll get the newer one
    pass

dev_requires = [
    "flake8>=2.5",
    "sphinx-rtd-theme>=0.1.9",
    "sphinx>=1.3",
    "pytest-reraise",
    "pytest>=6.1.1,<8.2.0",
] + tornado_requires

cmdclass = {}
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
      cmdclass=cmdclass,
      ext_modules=ext_modules,
      include_package_data=True,
)
