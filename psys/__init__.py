"""Provides various system utilities."""

from __future__ import unicode_literals

import errno
import os


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


# TODO:
#def close_all_fds(fds = []):
#	"""
#	Closes all opened file descriptors except stdin, stdout, stderr and fds.
#	"""
#
#	fd_num = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
#	if fd_num == resource.RLIM_INFINITY:
#		fd_num = constants.MAX_FDS
#
#	fds = set(fds)
#	for f in (sys.stdin, sys.stdout, sys.stderr):
#		if hasattr(f, "fileno"):
#			fds.add(f.fileno())
#
#	for fd in xrange(0, fd_num):
#		if fd not in fds:
#			try:
#				os.close(fd)
#			except:
#				pass
#
#While portable, closing all file descriptors up to sysconf(_SC_OPEN_MAX) is
#not reliable, because on most systems this call returns the current file
#descriptor soft limit, which could have been lowered below the highest used
#file descriptor. Another issue is that on many systems sysconf(_SC_OPEN_MAX)
#may return INT_MAX, which can cause this approach to be unacceptably slow.
#Unfortunately, there is no reliable, portable alternative that does not
#involve iterating over every possible non-negative int file descriptor.
#
#Although not portable, most operating systems in common use today provide one
#or more of the following solutions to this problem:
#
#A library function to close all file descriptors >= fd. This is the simplest
#solution for the common case of closing all file descriptors, although it
#cannot be used for much else. To close all file descriptors except for a
#certain set, dup2 can be used to move them to the low end beforehand, and to
#move them back afterward if necessary.
#
#closefrom(fd) (Solaris 9 or later, FreeBSD 7.3 or 8.0 and later, NetBSD 3.0 or
#later, OpenBSD 3.5 or later.)
#
#fcntl(fd, F_CLOSEM, 0) (AIX, IRIX, NetBSD)
#
#A library function to provide the maximum file descriptor currently in use by
#the process. To close all file descriptors above a certain number, either
#close all of them up to this maximum, or continually get and close the highest
#file descriptor in a loop until the low bound is reached. Which is more
#efficient depends on the file descriptor density.
#
#fcntl(0, F_MAXFD) (NetBSD)
#
#pstat_getproc(&ps, sizeof(struct pst_status), (size_t)0, (int)getpid())
#Returns information about the process, including the highest file descriptor
#currently open in ps.pst_highestfd. (HP-UX)
#
#A directory containing an entry for each open file descriptor. This is the
#most flexible approach as it allows for closing all file descriptors, finding
#the highest file descriptor, or doing just about anything else on every open
#file descriptor, even those of another process (on most systems). However this
#can be more complicated than the other approaches for the common uses. Also,
#it can fail for a variety of reasons such as proc/fdescfs not mounted, a
#chroot environment, or no file descriptors available to open the directory
#(process or system limit). Therefore use of this approach is often combined
#with a fallback mechanism. Example (OpenSSH), another example (glib).
#
#/proc/pid/fd/ or /proc/self/fd/ (Linux, Solaris, AIX, Cygwin, NetBSD) (AIX
#does not support "self".)
#
#/dev/fd/ (FreeBSD, Darwin)
#
#It can be difficult to handle all corner cases reliably with this approach.
#For example consider the situation where all file descriptors >= fd are to be
#closed, but all file descriptors < fd are used, the current process resource
#limit is fd, and there are file descriptors >= fd in use. Because the process
#resource limit has been reached the directory cannot be opened. If closing
#every file descriptor from fd through the resource limit or
#sysconf(_SC_OPEN_MAX) is used as a fallback, nothing will be closed.
