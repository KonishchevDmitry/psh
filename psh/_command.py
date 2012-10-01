"""Controls command executing."""

from __future__ import unicode_literals

import logging
import subprocess

import psys

from psh.exceptions import Error
from psh.exceptions import ExecutionError
from psh.exceptions import InvalidProcessState

LOG = logging.getLogger(__name__)


_PROCESS_STATE_PENDING = "pending"
"""Pending process state."""

_PROCESS_STATE_TERMINATED = "terminated"
"""Terminated process state."""


class Command:
    """Represents an executing command."""

    def __init__(self, program, *args, **kwargs):
        # Current state of the process
        self.__state = _PROCESS_STATE_PENDING

        # Program name or full path
        self.__program = program

        # Command's sys.argv
        self.__command = []


        # Success status codes for this command
        self.__ok_statuses = [ 0 ]


        # Command's stdout
        self.__stdout = r""

        # Command's stderr
        self.__stdout = r""

        # Command's termination status
        self.__status = None


        self.__parse_args(args, kwargs)

        LOG.debug("Executing %s", self.command_string())
        self.execute()


    def command(self):
        """Returns command arguments as it will be executed."""

        return self.__command[:]


    def command_string(self):
        """Returns command string as it will be executed."""

        command = ""

        for arg in self.__command:
            if command:
                command += " "

            if type(arg) == str:
                value = repr(arg)
                for c in b""" '"\\\r\n\t""":
                    if c in arg:
                        break
                else:
                    value = value.strip("'")
                command += value
            else:
                for c in b""" '"\\\r\n\t""":
                    if c in arg:
                        for replacement in (
                            ( b"\\", br"\\" ),
                            ( b"'",  br"\'" ),
                            ( b"\r", br"\r" ),
                            ( b"\n", br"\n" ),
                            ( b"\t", br"\t" ),
                        ):
                            arg = arg.replace(*replacement)

                        arg = "'" + arg + "'"
                        break
                command += arg

        return command

    # TODO
    def execute(self):
        #try:
        process = subprocess.Popen([ unicode(arg) for arg in self.__command ],
            stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout, stderr = process.communicate('')
        self.__status = process.returncode
        self.__state = _PROCESS_STATE_TERMINATED
        #except Exception as e:
        #    raise Error(str(e))

        self.__stdout = stdout
        self.__stderr = stderr

        if self.__status not in self.__ok_statuses:
            raise ExecutionError(self.__status, self.__stdout, self.__stderr)

    # TODO
    def __or__(self, command):
        """Shell-style pipelines."""

        LOG.debug("Creating a pipe: %s | %s", self.command_string(), command.command_string())
        return command


    def raw_stderr(self):
        """Returns the process' raw stderr."""

        return self.__stderr


    def raw_stdout(self):
        """Returns the process' raw stdout."""

        return self.__stdout


    def status(self):
        """Returns the process' exit status."""

        self.__ensure_terminated()
        return self.__status


    def stderr(self):
        """Returns the process' stderr."""

        return psys.u(self.__stderr)


    def stdout(self):
        """Returns the process' stdout."""

        return psys.u(self.__stdout)


    def __ensure_terminated(self):
        """Ensures that the process is terminated."""

        if self.__state != _PROCESS_STATE_TERMINATED:
            raise InvalidProcessState("Process is not terminated")


    def __parse_args(self, args, kwargs):
        """Parses command arguments and options."""

        self.__command.append(self.__program)

        for option, value in kwargs.iteritems():
            if option.startswith("_"):
                if option == "_ok_statuses":
                    self.__ok_statuses = [ int(status) for status in value ]
                else:
                    raise Error("Invalid option: {0}", option)
            elif len(option) == 1:
                self.__command.append("-" + option)
                if value is not None:
                    self.__command.append(_get_arg_value(value))
            else:
                self.__command.append("--" + option.replace("_", "-"))
                if value is not None:
                    self.__command.append(_get_arg_value(value))

        self.__command += [ _get_arg_value(arg) for arg in args ]


def _get_arg_value(value):
    """Returns an argument string value."""

    if type(value) in ( str, unicode ):
        return value
    elif type(value) in ( int, long, float ):
        return unicode(value)
    else:
        raise Error("Invalid argument: command arguments must be basic types only")
