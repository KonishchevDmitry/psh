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

    # TODO
    def __init__(self, program, *args, **kwargs):
        # Current state of the process
        self.__state = _PROCESS_STATE_PENDING

        self.__program = program

        self.__command = [ program ]
        # TODO kwargs
        self.__command += args


        # Success status codes for this command
        self.__ok_statuses = [ 0 ]


        # Command's stdout
        self.__stdout = r""

        # Command's stderr
        self.__stdout = r""

        # Command's termination status
        self.__status = None


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
            process = subprocess.Popen([ unicode(arg) for arg in self.__command ],
                stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            stdout, stderr = process.communicate('')
            self.__status = process.returncode
            self.__state = _PROCESS_STATE_TERMINATED
        except Exception:
            raise Error("ggg")

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
