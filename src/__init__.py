"""A Python package to interact with any program or device with a command line console.

Interactive is an interactive subprocess, it supports programmable console input/output
communication in real-time, direct connection to the console terminal, and
can run programs in parallel and check their output at anytime.
"""

__version_info__ = (1, 0, 1)
__version__ = '.'.join(map(str, __version_info__))
__author__ = "Dongsheng Mu"

__all__ = ['interact', 'pyssh', 'util']