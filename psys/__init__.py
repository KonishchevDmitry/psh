"""Provides various system utilities."""

from __future__ import unicode_literals

import errno
import os
import platform
import resource


BUFSIZE = 4096
"""I/O preferred buffer size."""


STDIN_FILENO = 0
"""Standard input descriptor."""

STDOUT_FILENO = 1
"""Standard output descriptor."""

STDERR_FILENO = 2
"""Standard error output descriptor."""


EXIT_SUCCESS = 0
"""Successful exit status."""

EXIT_FAILURE = 1
"""Failing exit status."""



def b(string):
    """Converts a unicode string to byte string in system encoding.

    For now always assumes UTF-8 as system encoding
    """

    if isinstance(string, unicode):
        return string.encode("utf-8")
    else:
        return string


def close_all_fds(except_fds = [ STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO ]):
    """Closes all opened file descriptors."""

    if platform.system() == "Darwin":
        fd_path = "/dev/fd"
    else:
        fd_path = "/proc/self/fd"

    try:
        opened_fds = [ int(fd) for fd in os.listdir(fd_path) ]
    except EnvironmentError:
        max_fd_num = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
        if max_fd_num == resource.RLIM_INFINITY:
            max_fd_num = 1024
        opened_fds = xrange(0, max_fd_num)

    for fd in opened_fds:
        if fd not in except_fds:
            try:
                eintr_retry(os.close)(fd)
            except EnvironmentError as e:
                if e.errno != errno.EBADF:
                    raise e


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


def join_thread(thread, timeout = None):
    """Joins the thread. Returns True if the thread terminated."""

    # Useful in 'finally'
    if thread is None:
        return True

    if timeout is None:
        # Python is buggy: if we simply join a thread in the main thread
        # without a timeout, we will never receive any UNIX signal.
        while thread.isAlive():
            thread.join(float(24 * 60 * 60))

        return True
    else:
        if timeout >= 0:
            thread.join(float(timeout))

        return thread.isAlive()


def u(string):
    """Converts a byte string in system encoding to unicode string.

    For now always assumes UTF-8 as system encoding
    """

    if isinstance(string, unicode):
        return string
    else:
        return string.decode("utf-8")
