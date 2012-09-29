"""Process management."""

from __future__ import unicode_literals

import logging
import subprocess
import sys

from types import ModuleType
LOG = logging.getLogger(__name__)


# TODO: just copypasted from sh project - refactor
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
        if attr[0].isupper() or attr.startswith("_"):
            return getattr(object.__getattribute__(self, "module"), attr)
        else:
            return Program(attr)
#    def __getattr__(self, name):
#        return self.env[name]

sys.modules[__name__] = SelfWrapper(sys.modules[__name__])


# TODO
class Error(Exception):
    """The base class for all exceptions this module throws."""

    def __init__(self, error, *args):
        Exception.__init__(self, unicode(error).format(*args) if len(args) else unicode(error))


class InvalidProcessState(Error):
    """
    Raised on attempt to process an operation on a process with an invalid
    state for this operation.
    """

    def __init__(self, *args, **kwargs):
        super(InvalidProcessState, self).__init__(*args, **kwargs)


class ExecutionError(Error):
    """Raised when command failed to execute."""

    def __init__(self, status = 127):
        super(ExecutionError, self).__init__("Command execution failed")
        self.status = status


PROCESS_STATE_PENDING = "pending"
"""Pending process state."""

PROCESS_STATE_TERMINATED = "terminated"
"""Terminated process state."""


class Command:
    """Represents an executing command."""

    # TODO
    def __init__(self, program, *args, **kwargs):
        # Current state of the process
        self.__state = PROCESS_STATE_PENDING

        self.__program = program

        self.__command = [ program ]
        # TODO kwargs
        self.__command += args

        # Success status codes for this command
        self.__ok_statuses = [ 0 ]

        for option in kwargs.keys():
            if option.startswith("_"):
                value = kwargs[option]

                if option == "_ok_statuses":
                    self.__ok_statuses = [ int(status) for status in value ]
                else:
                    raise Error("Invalid option: {0}", option)

                del kwargs[option]

        LOG.debug("Executing %s", self.command_string())
        self.execute()

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

    # TODO
    def execute(self):
        try:
            process = subprocess.Popen([ unicode(arg) for arg in self.__command ])
            stdout, stderr = process.communicate('')
            self.__status = process.returncode
            self.__state = PROCESS_STATE_TERMINATED
        except Exception:
            raise Error("ggg")

        if self.__status not in self.__ok_statuses:
            raise ExecutionError(self.__status)

    # TODO
    def __or__(self, command):
        """Shell-style pipelines."""

        LOG.debug("Creating a pipe: %s | %s", self.command_string(), command.command_string())
        return command


    def status(self):
        """Returns the process exit status."""

        self.__ensure_terminated()
        return self.__status


    def __ensure_terminated(self):
        """Ensures that the process is terminated."""

        if self.__state != PROCESS_STATE_TERMINATED:
            raise InvalidProcessState("Process is not terminated")


# TODO
class Program:
    """Represents a program."""

    def __init__(self, program):
        self.__program = program

    def __call__(self, *args, **kwargs):
        return Command(self.__program, *args, **kwargs)
