"""Waiting for I/O completion."""

from __future__ import unicode_literals

import errno
import logging
import select
import time

import psys
from psys import eintr_retry

LOG = logging.getLogger(__name__)


class _Poll(object):
    """Base class for all poll objects."""

    POLLIN = 1
    """Available for read."""

    POLLOUT = 2
    """Available for write."""


    def __del__(self):
        self.close()


    def close(self):
        """Closes the object."""


    def poll(self, timeout = None):
        """Waits for events."""

        raise Exception("Not implemented")


    def register(self, fd, flags):
        """Registers a file descriptor with the poll object."""

        raise Exception("Not implemented")


    def unregister(self, fd):
        """Remove a file descriptor being tracked by a polling object."""

        raise Exception("Not implemented")



if hasattr(select, "epoll"):
    class Poll(_Poll):
        """epoll implementation."""

        def __init__(self):
            super(Poll, self).__init__()
            self.__epoll = select.epoll()


        def close(self):
            """Closes the object."""

            if self.__epoll is not None:
                try:
                    eintr_retry(self.__epoll.close)()
                except Exception as e:
                    LOG.error("Unable to close an epoll instance: %s.", psys.e(e))
                else:
                    self.__epoll = None


        def poll(self, timeout = None):
            """Waits for events."""

            if self.__epoll is None:
                raise Exception("The poll object is closed")

            if timeout is None:
                timeout = -1
            elif timeout < 0:
                timeout = 0

            if timeout > 0:
                end_time = time.time() + timeout

            while True:
                try:
                    epoll_events = self.__epoll.poll(timeout)
                except EnvironmentError as e:
                    if e.errno == errno.EINTR:
                        if timeout > 0:
                            timeout = max(0, end_time - time.time())
                    else:
                        raise e
                else:
                    break

            events = []

            for fd, epoll_flags in epoll_events:
                flags = 0

                if epoll_flags & select.EPOLLIN:
                    flags |= self.POLLIN

                if epoll_flags & select.EPOLLOUT:
                    flags |= self.POLLOUT

                events.append(( fd, flags ))

            return events


        def register(self, fd, flags):
            """Register a file descriptor with the poll object."""

            if self.__epoll is None:
                raise Exception("The poll object is closed")

            epoll_flags = 0

            if flags & self.POLLIN:
                epoll_flags |= select.EPOLLIN

            if flags & self.POLLOUT:
                epoll_flags |= select.EPOLLOUT

            self.__epoll.register(fd, epoll_flags)


        def unregister(self, fd):
            """Remove a file descriptor being tracked by a polling object."""

            self.__epoll.unregister(fd)
else:
    class Poll(_Poll):
        """select implementation."""

        def __init__(self):
            super(Poll, self).__init__()
            self.__rlist = []
            self.__wlist = []


        def poll(self, timeout = None):
            """Waits for events."""

            if timeout is not None:
                if timeout < 0:
                    timeout = 0
                elif timeout > 0:
                    end_time = time.time() + timeout

            while True:
                try:
                    rlist, wlist, xlist = select.select(
                        self.__rlist, self.__wlist, [], timeout)
                except EnvironmentError as e:
                    if e.errno == errno.EINTR:
                        if timeout is not None and timeout > 0:
                            timeout = max(0, end_time - time.time())
                    else:
                        raise e
                else:
                    break

            events = []

            for fd in set(rlist + wlist):
                flags = 0

                if fd in rlist:
                    flags |= self.POLLIN

                if fd in wlist:
                    flags |= self.POLLOUT

                events.append(( fd, flags ))

            return events


        def register(self, fd, flags):
            """Registers a file descriptor with the poll object."""

            if flags & self.POLLIN and fd not in self.__rlist:
                self.__rlist.append(fd)

            if flags & self.POLLOUT and fd not in self.__wlist:
                self.__wlist.append(fd)


        def unregister(self, fd):
            """Remove a file descriptor being tracked by a polling object."""

            try:
                self.__rlist.remove(fd)
            except ValueError:
                pass

            try:
                self.__wlist.remove(fd)
            except ValueError:
                pass
