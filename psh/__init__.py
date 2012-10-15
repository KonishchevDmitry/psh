from __future__ import unicode_literals

from psh.process import Process
from psh.process import STDIN, STDOUT, STDERR, PIPE, File, DEVNULL
from psh.exceptions import Error, ExecutionError, InvalidArgument, InvalidOperation, InvalidProcessState, ProcessOutputWasTruncated


class Sh(object):
    """Program object factory."""

    def __init__(self, **kwargs):
        for option in kwargs:
            if not option.startswith("_"):
                raise InvalidArgument("Invalid argument: all options must start with '_'")

        # Default process options
        self._default_options = kwargs


    def __getattribute__(self, attr):
        """Creates a Program instance."""

        return Program(attr.replace("_", "-"),
            **object.__getattribute__(self, "_default_options"))


    def __call__(self, program):
        """Creates a Program instance."""

        return Program(program,
            **object.__getattribute__(self, "_default_options"))


class Program:
    """Represents an executable program."""

    def __init__(self, program, *args, **kwargs):
        # Default process arguments
        self.__args = ( program, ) + args

        # Default process options
        self.__kwargs = kwargs


    def __call__(self, *args, **kwargs):
        """Creates a :py:class:`Process` instance for this program."""

        args = self.__args + args

        options = self.__kwargs.copy()
        options.update(kwargs)

        return Process(*args, **options)


sh = Sh()
"""Default :py:class:`Program` object factory."""
