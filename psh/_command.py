"""Controls command executing."""

from __future__ import unicode_literals

import errno
import logging
import os

import psys
from psys import eintr_retry

from psh.exceptions import Error
from psh.exceptions import ExecutionError
from psh.exceptions import InvalidProcessState

LOG = logging.getLogger(__name__)


_PROCESS_STATE_PENDING = "pending"
"""Pending process state."""

_PROCESS_STATE_RUNNING = "running"
"""Running process state."""

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

        # Command's pipes
        self.__pipes = []


        # Success status codes for this command
        self.__ok_statuses = [ 0 ]


        # PID of the process
        self.__pid = None

        # Command's stdout
        self.__stdout = r""

        # Command's stderr
        self.__stderr = r""

        # Command's termination status
        self.__status = None


        self.__parse_args(args, kwargs)

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


    def execute(self):
        """Executes the command."""
        # TODO: exceptions

        LOG.debug("Executing %s", self.command_string())

        # TODO: close
        for fd in ( 0, 1, 2 ):
            self.__pipes.append(_Pipe(fd, output = bool(fd)))

        self.__pid = os.fork()

        if self.__pid:
            self.__state = _PROCESS_STATE_RUNNING

            for pipe in self.__pipes:
                pipe.close(read = not pipe.output, write = pipe.output)

            status = eintr_retry(os.waitpid)(self.__pid, 0)[1]

            if os.WIFEXITED(status):
                self.__status = os.WEXITSTATUS(status)
                LOG.debug("Command %s terminated with %s status code.",
                    self.command_string(), self.__status)
            elif os.WIFSIGNALED(status):
                signum = os.WTERMSIG(status)
                LOG.debug("Command %s terminated due to receipt of %s signal.",
                    self.command_string(), signum)
                self.__status = 128 + signum
            else:
                LOG.error("Command %s terminated due to unknown reason.", self.command_string())
                self.__status = 126

            self.__stdout = eintr_retry(os.read)(self.__pipes[1].read, 4096)
            self.__stderr = eintr_retry(os.read)(self.__pipes[2].read, 4096)

            self.__state = _PROCESS_STATE_TERMINATED
        else:
            exit_code = 127

            try:
                exec_error = False

                try:
                    for pipe in self.__pipes:
                        try:
                            eintr_retry(os.dup2)(pipe.write if pipe.output else pipe.read, pipe.source)
                        except Exception as e:
                            raise Error("Unable to connect a pipe to file descriptor {0}: {1}", pipe.source, psys.e(e))

                        pipe.close()

                    exec_error = True
                    os.execvp(self.__program, self.__command)
                except Exception as e:
                    if exec_error and isinstance(e, EnvironmentError) and e.errno == errno.EACCES:
                        exit_code = 126

                    os.write(2, "Failed to execute '{program}': {error}.\n".format(
                        program = self.__program, error = psys.e(e)))
            finally:
                os._exit(exit_code)

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



class _Pipe():
    """Represents a pipe between two processes."""

    def __init__(self, source, output = True):
        # File descriptor that we are going to replace by this pipe
        self.source = source

        # True if this is output file descriptor
        self.output = output

        try:
            self.read, self.write = os.pipe()
        except Exception as e:
            raise Error("Unable to create a pipe: {0}.", psys.e(e))


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



def _get_arg_value(value):
    """Returns an argument string value."""

    if type(value) in ( str, unicode ):
        return value
    elif type(value) in ( int, long, float ):
        return unicode(value)
    else:
        raise Error("Invalid argument: command arguments must be basic types only")
