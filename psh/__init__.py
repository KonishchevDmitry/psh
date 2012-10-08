"""Process management."""

from __future__ import unicode_literals

from psh._command import Process


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
        return Process(self.__program, *args, **kwargs)


from psh.exceptions import *
sh = Sh()
