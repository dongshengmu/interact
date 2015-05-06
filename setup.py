#!/usr/bin/env python

from distutils.core import setup


classifiers = """\
Development Status :: 5 - Production/Stable
Intended Audience :: Developers
License :: OSI Approved :: MIT License
Environment :: Console
Programming Language :: Python
Programming Language :: Python :: 2
Programming Language :: Python :: 2.6
Programming Language :: Python :: 2.7
Operating System :: OS Independent
Topic :: Software Development :: Libraries :: Python Modules
Topic :: Software Development :: Documentation
Topic :: Software Development :: Testing
"""


setup(
    name="Interactive",
    version="1.0.1",
    maintainer="Dongsheng Mu",
    maintainer_email="dongshengm@gmail.com",
    author="Dongsheng Mu",
    author_email="dongshengm@gmail.com",
    url="https://github.com/dongshengmu/interact",
    license="MIT",
    platforms=["any"],
    package_dir={"Interactive": "src"},
    packages=['Interactive'],
    description="A package to interact with any program with a command line console.",
    classifiers=filter(None, classifiers.split("\n")),
    long_description="""A Python package to interact with any program or device with a command line console.

Interactive is a interactive subprocess, it supports programmable input/output
communication in real-time, direct connection to the console terminal, and
can run programs in parallel and check their output at anytime.
""",
)
