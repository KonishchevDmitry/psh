from __future__ import unicode_literals

from psh.process import Process
from psh.process import STDIN, STDOUT, STDERR, PIPE, File, DEVNULL
from psh.exceptions import Error, ExecutionError, InvalidArgument, InvalidOperation, InvalidProcessState, ProcessOutputWasTruncated


class Sh(object):
    """:py:class:`Program` object factory."""

    def __init__(self, **default_options):
        for option in default_options:
            if not option.startswith("_"):
                raise InvalidArgument("Invalid argument: all options must start with '_'")

        # Default process options
        self._default_options = default_options


    def __call__(self, program):
        """Creates a :py:class:`Program` instance."""

        return Program(program,
            **object.__getattribute__(self, "_default_options"))


    def __getattribute__(self, program):
        """Creates a :py:class:`Program` instance."""

        return Program(program.replace("_", "-"),
            **object.__getattribute__(self, "_default_options"))


class Program:
    """Represents an executable program."""

    def __init__(self, program, *default_args, **default_options):
        # Default process arguments
        self.__args = ( program, ) + default_args

        # Default process options
        self.__options = default_options


    def __call__(self, *args, **options):
        """Creates a :py:class:`Process` instance for this program."""

        result_args = self.__args + args

        result_options = self.__options.copy()
        result_options.update(options)

        return Process(*result_args, **result_options)


sh = Sh()
"""Default :py:class:`Program` object factory."""
