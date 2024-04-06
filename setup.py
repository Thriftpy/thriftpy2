#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import sys
import platform

from os.path import join, dirname

from setuptools import setup, find_packages
from setuptools.extension import Extension

with open(join(dirname(__file__), 'thriftpy2', '__init__.py'), 'r') as f:
    version = re.match(r".*__version__ = '(.*?)'", f.read(), re.S).group(1)

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
    "pytest>=2.8",
    "sphinx-rtd-theme>=0.1.9",
    "sphinx>=1.3",
    "pytest>=6.1.1",
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
    ext_modules.append(Extension("thriftpy2.protocol.cybin",
                                 ["thriftpy2/protocol/cybin/cybin.c"],
                                 libraries=libraries))

setup(name="thriftpy2",
      version=version,
      description="Pure python implementation of Apache Thrift.",
      keywords="thrift python thriftpy thriftpy2",
      author="ThriftPy Organization",
      author_email="gotzehsing@gmail.com",
      packages=find_packages(exclude=['benchmark', 'docs', 'tests']),
      entry_points={},
      url="https://thriftpy2.readthedocs.io/",
      project_urls={
          "Source": "https://github.com/Thriftpy/thriftpy2",
      },
      license="MIT",
      zip_safe=False,
      long_description=open("README.rst").read(),
      install_requires=install_requires,
      tests_require=tornado_requires,
      python_requires='>=3.6',
      extras_require={
          "dev": dev_requires,
          "tornado": tornado_requires
      },
      cmdclass=cmdclass,
      ext_modules=ext_modules,
      include_package_data=True,
      classifiers=[
          "Topic :: Software Development",
          "Development Status :: 4 - Beta",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: MIT License",
          "Programming Language :: Python :: 3",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: 3.7",
          "Programming Language :: Python :: 3.8",
          "Programming Language :: Python :: 3.9",
          "Programming Language :: Python :: 3.10",
          "Programming Language :: Python :: 3.11",
          "Programming Language :: Python :: 3.12",
          "Programming Language :: Python :: Implementation :: CPython",
          "Programming Language :: Python :: Implementation :: PyPy",
      ])
