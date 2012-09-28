"""Process management."""

from __future__ import unicode_literals

import logging
import sys

from types import ModuleType
LOG = logging.getLogger(__name__)


# TODO
# this is a thin wrapper around THIS module (we patch sys.modules[__name__]).
# this is in the case that the user does a "from sh import whatever"
# in other words, they only want to import certain programs, not the whole
# system PATH worth of commands.  in this case, we just proxy the
# import lookup to our Environment class
class SelfWrapper(ModuleType):
    def __init__(self, module):
        # this is super ugly to have to copy attributes like this,
        # but it seems to be the only way to make reload() behave
        # nicely.  if i make these attributes dynamic lookups in
        # __getattr__, reload sometimes chokes in weird ways...
        for attr in ["__builtins__", "__doc__", "__name__", "__package__"]:
            setattr(self, attr, getattr(module, attr))

        self.module = module

    def __getattribute__(self, attr):
        return Program(attr)
        return getattr(object.__getattribute__(self, "module"), attr)
#    def __getattr__(self, name):
#        return self.env[name]

sys.modules[__name__] = SelfWrapper(sys.modules[__name__])


class Command:
    """Represents an executing command."""

    def __init__(self, program, *args, **kwargs):
        self.__program = program

        self.__command = [ program ]
        # TODO kwargs
        self.__command += args

        LOG.debug("Executing %s", self.command_string())

    # TODO
    def command_string(self):
        """Returns command string."""

        command = ""
        for arg in self.__command:
            arg = unicode(arg)
            if " " in arg:
                arg = "'" + arg + "'"
            if command:
                command += " "
            command += arg
        return command

    def __or__(self, command):
        """Shell-style pipelines."""

        LOG.debug("Creating a pipe: %s | %s", self.command_string(), command.command_string())
        return command

class Program:
    """Represents a program."""

    def __init__(self, program):
        self.__program = program

    def __call__(self, *args, **kwargs):
        return Command(self.__program, *args, **kwargs)
