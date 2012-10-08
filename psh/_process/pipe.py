"""Provides a UNIX pipe class."""

from __future__ import unicode_literals

import logging
import os

import psys
import psys.poll
from psys import eintr_retry

import psh
from psh.exceptions import Error

LOG = logging.getLogger(__name__)


class Pipe():
    """Represents a pipe between two processes."""

    def __init__(self, source, output = True, pipe = None):
        # File descriptor that we are going to replace by this pipe
        self.source = source

        # True if this is output file descriptor
        self.output = output

        if pipe is None:
            try:
                self.read, self.write = os.pipe()
            except Exception as e:
                raise Error("Unable to create a pipe: {0}.", psys.e(e))
        else:
            if output:
                self.read = None
                self.write = pipe.write
                pipe.write = None
            else:
                self.read = pipe.read
                pipe.read = None
                self.write = None


    def __del__(self):
        # Don't close the object in unit tests to be able to detect leaks
        if not hasattr(psh, "_UNIT_TEST"):
            self.close()


    def close(self, read = True, write = True):
        """Closes the pipe."""

        if read and self.read is not None:
            try:
                eintr_retry(os.close)(self.read)
            except Exception as e:
                LOG.error("Unable to close a pipe: %s.", psys.e(e))
            else:
                self.read = None

        if write and self.write is not None:
            try:
                eintr_retry(os.close)(self.write)
            except Exception as e:
                LOG.error("Unable to close a pipe: %s.", psys.e(e))
            else:
                self.write = None
