"""Contains all exceptions generated by the library."""

from __future__ import unicode_literals

import psys


class Error(Exception):
    """A base class for all exceptions the module throws."""

    def __init__(self, error, *args, **kwargs):
        super(Error, self).__init__(
            error.format(*args, **kwargs) if args or kwargs else error)


class ExecutionError(Error):
    """
    Raised when a command fails to execute or returns an error exit status
    code.
    """

    def __init__(self, command, status, stdout, stderr,
        error = "Program terminated with an error status"):

        super(ExecutionError, self).__init__(error)
        self.__command = command
        self.__status = status
        self.__stdout = stdout
        self.__stderr = stderr


    def command(self):
        """Returns the process command string."""

        return self.__command


    def raw_stderr(self):
        """
        Returns the process' captured raw stderr (if ``_stderr = PIPE``).
        """

        return self.__stderr


    def raw_stdout(self):
        """
        Returns the process' captured raw stdout (if ``_stdout = PIPE``).
        """

        return self.__stdout


    def status(self):
        """Returns the process's exit status."""

        return self.__status


    def stderr(self):
        """Returns the process' captured stderr (if ``_stderr = PIPE``)."""

        return psys.u(self.__stderr)


    def stdout(self):
        """Returns the process' captured stdout (if ``_stdout = PIPE``)."""

        return psys.u(self.__stdout)


class InvalidArgument(Error):
    """Raised on attempt to start a process with an invalid argument."""

    def __init__(self, *args, **kwargs):
        super(InvalidArgument, self).__init__(*args, **kwargs)


class InvalidOperation(Error):
    """Raised on attempt to process an invalid operation on a process."""

    def __init__(self, *args, **kwargs):
        super(InvalidOperation, self).__init__(*args, **kwargs)


class InvalidProcessState(Error):
    """
    Raised on attempt to process an operation on a process with an invalid
    state for this operation.
    """

    def __init__(self, *args, **kwargs):
        super(InvalidProcessState, self).__init__(*args, **kwargs)


class LogicalError(Error):
    """Logical error."""

    def __init__(self, *args, **kwargs):
        super(Error, self).__init__("Logical error")


class ProcessOutputWasTruncated(ExecutionError):
    """
    Raised when process terminates and its output is truncated because one of
    its children didn't close the output descriptor.
    """

    def __init__(self, command, status, stdout, stderr):
        super(ProcessOutputWasTruncated, self).__init__(
            command, status, stdout, stderr, error = "The process' output was truncated")
