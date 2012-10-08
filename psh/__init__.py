"""Process management."""

from __future__ import unicode_literals

import psh.process


class Sh(object):
    """An object that allows to run commands in the shell-style way."""

    def __getattribute__(self, attr):
        return Program(attr)


class Program:
    """Represents a program."""

    def __init__(self, program):
        # Program name or full path
        self.__program = program


    def __call__(self, *args, **kwargs):
        return psh.process.Process(self.__program, *args, **kwargs)


from psh.exceptions import Error, ExecutionError, InvalidArgument, InvalidOperation, InvalidProcessState
sh = Sh()
