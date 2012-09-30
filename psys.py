"""Provides various system utilities."""

from __future__ import unicode_literals

# TODO
#def syscall_wrapper(func, *args, **kwargs):
#    """Calls func() ignoring EINTR error."""
#
#    while True:
#        try:
#            return func(*args, **kwargs)
#        except EnvironmentError as e:
#            if e.errno == errno.EINTR:
#                pass
#            else:
#                raise


def b(string):
    """Converts a unicode string to byte string in system encoding.

    For now always assumes UTF-8 as system encoding
    """

    if isinstance(string, unicode):
        return string.encode("utf-8")
    else:
        return string


def u(string):
    """Converts a byte string in system encoding to unicode string.

    For now always assumes UTF-8 as system encoding
    """

    if isinstance(string, unicode):
        return string
    else:
        return string.decode("utf-8")
