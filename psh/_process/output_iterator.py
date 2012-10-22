"""Provides an iterator over process output."""

from __future__ import unicode_literals

import fcntl
import logging
import os

from pcore import PY3

import psys
import psys.poll
from psys import eintr_retry

import psh
from psh.exceptions import InvalidOperation
from psh._process.pipe import Pipe

LOG = logging.getLogger(__name__)


class OutputIterator:
    """Process output iterator."""

    def __init__(self, process, raw, delimiter):
        # The process
        self.__process = process

        # Raw or unicode string iteration
        self.__raw = raw

        # Block delimiter
        self.__delimiter = delimiter

        # Output pipe
        self.__pipe = None

        # Polling object
        self.__poll = None

        # Output data buffer. None indicates EOF.
        self.__data = b""

        # Is the iterator closed
        self.__closed = False

        if delimiter:
            self.__iter = self.__iter_with_delimiter
        else:
            if raw:
                self.__iter = self.__iter_without_delimiter
            else:
                raise InvalidOperation("Can't iterate over unicode data without delimiter")

        try:
            self.__pipe = Pipe(psys.STDOUT_FILENO)
            flags = eintr_retry(fcntl.fcntl)(self.__pipe.read, fcntl.F_GETFL)
            eintr_retry(fcntl.fcntl)(self.__pipe.read, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self.__poll = psys.poll.Poll()
            self.__poll.register(self.__pipe.read, self.__poll.POLLIN)
        except:
            self.close()
            raise


    def __del__(self):
        # Don't close the object in unit tests to be able to detect leaks
        if not hasattr(psh, "_UNIT_TEST"):
            self.close()


    def close(self):
        """Closes the iterator."""

        if self.__closed:
            return

        if self.__poll is not None:
            self.__poll.close()

        if self.__pipe is not None:
            self.__pipe.close()

        self.__closed = True


    def pipe(self):
        """Returns the output pipe."""

        return self.__pipe


    def __finalize(self, check_status = True):
        """Finalizes the iterator (on error or when we read all data)."""

        self.close()
        self.__process.wait(check_status)


    def __iter_with_delimiter(self):
        """Iterates over the data splitting it with the delimiter."""

        try:
            pos = self.__data.index(self.__delimiter)
        except ValueError:
            while True:
                try:
                    self.__poll.poll()
                    data = eintr_retry(os.read)(self.__pipe.read, psys.BUFSIZE)
                except:
                    self.__finalize(check_status = False)
                    raise

                if data:
                    try:
                        pos = data.index(self.__delimiter)
                    except ValueError:
                        self.__data += data
                    else:
                        block = self.__data + data[:pos + 1]
                        self.__data = data[pos + 1:]
                        return self.__transform_block(block)
                else:
                    block = self.__data
                    self.__data = None
                    self.__finalize()

                    if not block:
                        raise StopIteration()

                    return self.__transform_block(block)
        else:
            block = self.__data[:pos + 1]
            self.__data = self.__data[pos + 1:]
            return self.__transform_block(block)


    def __iter_without_delimiter(self):
        """Iterates over the data."""

        try:
            self.__poll.poll()
            data = eintr_retry(os.read)(self.__pipe.read, psys.BUFSIZE)
        except:
            self.__finalize()
            raise
        else:
            if not data:
                self.__data = None
                self.__finalize()
                raise StopIteration()

            return data


    def __next(self):
        """Iterator's 'next' method."""

        if self.__data is None:
            raise StopIteration()

        if self.__closed:
            raise InvalidOperation("The iterator is closed")

        return self.__iter()


    def __transform_block(self, block):
        """Transforms the data block to the output format."""

        if self.__raw:
            return block
        else:
            try:
                return psys.u(block)
            except:
                self.__finalize()
                raise


    if PY3:
        __next__ = __next
    else:
        next = __next
