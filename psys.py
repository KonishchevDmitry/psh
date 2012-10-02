"""Provides various system utilities."""

from __future__ import unicode_literals

import errno
import os


def b(string):
    """Converts a unicode string to byte string in system encoding.

    For now always assumes UTF-8 as system encoding
    """

    if isinstance(string, unicode):
        return string.encode("utf-8")
    else:
        return string


def e(error):
    """Returns an exception error string."""

    return os.strerror(error.errno) if isinstance(error, EnvironmentError) else unicode(error)


def eintr_retry(func):
    """Wraps the function to retry calls ended up with EINTR."""

    def wrapper(*args, **kwargs):
        while True:
            try:
                return func(*args, **kwargs)
            except EnvironmentError as e:
                if e.errno != errno.EINTR:
                    raise e

    return wrapper


def u(string):
    """Converts a byte string in system encoding to unicode string.

    For now always assumes UTF-8 as system encoding
    """

    if isinstance(string, unicode):
        return string
    else:
        return string.decode("utf-8")
