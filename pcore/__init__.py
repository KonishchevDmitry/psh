"""Provides various core tools."""

from __future__ import unicode_literals

import sys


PY3 = sys.version_info.major == 3
"""True if we are running under Python 3."""

if PY3:
    range = range
else:
    range = xrange

if PY3:
    bytes = bytes
    str = str
else:
    bytes = str
    str = unicode
