"""Controls command executing."""

from __future__ import unicode_literals

import cStringIO
import errno
import fcntl
import logging
import os
import signal
import sys
import threading
import time

import psys
import psys.poll
from psys import eintr_retry

from psh.exceptions import Error, LogicalError
from psh.exceptions import ExecutionError
from psh.exceptions import InvalidOperation
from psh.exceptions import InvalidProcessState

LOG = logging.getLogger(__name__)


_PROCESS_STATE_PENDING = 0
"""Pending process state."""

_PROCESS_STATE_SPAWNING = 1
"""Spawning process state."""

_PROCESS_STATE_RUNNING = 2
"""Running process state."""

_PROCESS_STATE_TERMINATED = 3
"""Terminated process state."""


class Command:
    """Represents an executing command.

    All public methods are thread-safe.
    """

    def __init__(self, program, *args, **kwargs):
        # Data lock
        self.__lock = threading.Lock()

        # Current state of the process
        self.__state = _PROCESS_STATE_PENDING


        # Program name or full path
        self.__program = program

        # Command's sys.argv
        self.__command = []


        # The process' custom stdin source (another process)
        self.__stdin_source = None

        # The process' custom stdout target (another process)
        self.__stdout_target = None

        # Success status codes for this command
        self.__ok_statuses = [ psys.EXIT_SUCCESS ]


        # Command's pipes
        self.__pipes = []

        # A pipe to signal about the process termination
        self.__termination_fd = None

        # A thread in which we communicate with the process
        self.__communication_thread = None

        # A thread in which we wait for process termination
        self.__wait_thread = None


        # PID of the process
        self.__pid = None

        # Command's stdout
        self.__stdout = cStringIO.StringIO()

        # Command's stderr
        self.__stderr = cStringIO.StringIO()

        # Command's termination status
        self.__status = None


        # Parse the command arguments
        self.__parse_args(args, kwargs)


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


    def execute(self, wait = True):
        """Executes the command."""

        self._execute()

        if wait:
            self.wait(check_status = True)

        return self


    def kill(self, signal = signal.SIGTERM):
        """Kills the process.

        Returns True if the process received the signal.
        """

        if self.__state < _PROCESS_STATE_RUNNING:
            raise InvalidProcessState("Process is not running")

        if self.__state == _PROCESS_STATE_RUNNING:
            LOG.debug("Send %s signal to %s...", signal, self.command_string())

            try:
                os.kill(self.__pid, signal)
            except EnvironmentError as e:
                if e.errno != errno.ESRCH:
                    raise e
            else:
                return True

        return False


    def pid(self):
        """Returns the process' PID."""

        if self.__state < _PROCESS_STATE_RUNNING:
            raise InvalidProcessState("Process is not running")

        return self.__pid


    def raw_stderr(self):
        """Returns the process' raw stderr."""

        self.__ensure_terminated()
        return self.__stderr.getvalue()


    def raw_stdout(self):
        """Returns the process' raw stdout."""

        self.__ensure_terminated()
        return self.__stdout.getvalue()


    def status(self):
        """Returns the process' exit status."""

        self.__ensure_terminated()
        return self.__status


    def stderr(self):
        """Returns the process' stderr."""

        return psys.u(self.raw_stderr())


    def stdout(self):
        """Returns the process' stdout."""

        return psys.u(self.raw_stdout())


    def wait(self, check_status = False, kill = None):
        """Waits for the process termination.

        If kill is not None kills the process with the signal == kill and
        waits for its termination.
        """

        if self.__state < _PROCESS_STATE_RUNNING:
            raise InvalidProcessState("Process is not running")

        LOG.debug("Waiting for %s termination%s...", self.command_string(),
            "" if kill is None else " killing it with {0} signal".format(kill))

        if kill is not None:
            while self.kill(kill):
                if self.__join_threads(0.1):
                    break

        self.__join_threads()

        if self.__stdin_source is not None:
            self.__stdin_source.wait(
                check_status = check_status, kill = kill)

        if check_status and self.__status not in self.__ok_statuses:
            raise ExecutionError(self.__status, self.raw_stdout(), self.raw_stderr())

        return self.__status


    def _execute(self, stdout = None, check_pipes = True):
        """Executes the command."""

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidOperation("The process has been executed already")

            if check_pipes and self.__stdout_target is not None:
                raise InvalidOperation("Only the last process of the pipe can be executed")

            self.__state = _PROCESS_STATE_SPAWNING

        LOG.debug("Executing %s", self.command_string())

        try:
            self.__execute(stdout)
        except Exception as e:
            self.__close()
            self.__join_threads()

            if (
                self.__stdin_source is not None and
                self.__stdin_source._state() >= _PROCESS_STATE_RUNNING
            ):
                self.__stderr.wait(kill = signal.SIGTERM)

            raise e


    def _pipe_process(self, command):
        """Creates a pipe between two processes."""

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidProcessState("Process can't be piped after execution")

            if self.__stdin_source is not None:
                raise InvalidOperation("The process' stdin is already redirected")

            LOG.debug("Creating a pipe: %s | %s", command.command_string(), self.command_string())

            self.__stdin_source = command


    def _state(self):
        """Returns current process state."""

        return self.__state


    def __child(self):
        """Handles child process execution."""

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

                psys.close_all_fds()

                exec_error = True
                os.execvp(self.__program, self.__command)
            except Exception as e:
                if exec_error and isinstance(e, EnvironmentError) and e.errno == errno.EACCES:
                    exit_code = 126

                print >> sys.stderr, "Failed to execute '{program}': {error}.".format(
                    program = self.__program, error = psys.e(e))
        finally:
            os._exit(exit_code)


    def __close(self):
        """
        Frees all allocated resources unneeded after the process termination
        or its failed execution.
        """

        for pipe in self.__pipes:
            pipe.close()
        del self.__pipes[:]

        if self.__termination_fd is not None:
            try:
                eintr_retry(os.close)(self.__termination_fd)
            except Exception as e:
                LOG.error("Unable to close a pipe: %s.", psys.e(e))
            else:
                self.__termination_fd = None


    def __communicate(self, poll):
        """Communicates with the process and waits for its termination."""

        pipe_map = {}

        # Configure the poll object and pipes -->
        poll.register(self.__termination_fd, poll.POLLIN)

        for pipe in self.__pipes:
            fd = pipe.read if pipe.output else pipe.write
            if fd is None:
                continue

            pipe_map[fd] = pipe

            flags = eintr_retry(fcntl.fcntl)(fd, fcntl.F_GETFL)
            eintr_retry(fcntl.fcntl)(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            poll.register(fd, poll.POLLIN if pipe.output else poll.POLLOUT)
            pipe.close(read = not pipe.output, write = pipe.output)
        # Configure the poll object and pipes <--


        # Communicate with the process until it terminates...

        stdin = None
        terminated = False

        while not terminated:
            for fd, flags in poll.poll():
                # Process termination
                if fd == self.__termination_fd:
                    terminated = True
                    break

                pipe = pipe_map[fd]

                # stdin
                if pipe.source == psys.STDIN_FILENO:
                    if stdin is None:
                        stdin = self.__on_input()

                    if stdin is None:
                        poll.unregister(fd)
                        pipe.close()
                    else:
                        try:
                            size = eintr_retry(os.write)(fd, stdin)
                        except EnvironmentError as e:
                            # The process closed its stdin
                            if e.errno == errno.EPIPE:
                                poll.unregister(fd)
                                pipe.close()
                            else:
                                raise e
                        else:
                            if size == len(stdin):
                                stdin = None
                            else:
                                stdin = stdin[size:]
                # stdout/stderr
                elif pipe.source in ( psys.STDOUT_FILENO, psys.STDERR_FILENO ):
                    data = eintr_retry(os.read)(fd, psys.BUFSIZE)

                    if data:
                        self.__on_output(pipe.source, data)
                    else:
                        poll.unregister(fd)
                else:
                    raise LogicalError()


        # The process has terminated, but we should continue communication to
        # get output that we haven't got from it yet. But we must do it
        # wisely, because the process might fork() itself so we'll read its
        # child's output forever.

        # Maximum output size after process termination
        max_data_size = 1024 * 1024

        for pipe in self.__pipes:
            if (
                pipe.source in ( psys.STDOUT_FILENO, psys.STDERR_FILENO ) and
                pipe.read is not None
            ):
                size = 0

                while size < max_data_size:
                    try:
                        data = eintr_retry(os.read)(
                            pipe.read, min(psys.BUFSIZE, max_data_size - size))
                    except EnvironmentError as e:
                        if e.errno == errno.EAGAIN:
                            break
                        else:
                            raise e
                    else:
                        if data:
                            size += len(data)
                            self.__on_output(pipe.source, data)
                        else:
                            break


    def __communication_thread_func(self, fork_lock, poll):
        """A thread in which we communicate with the process."""

        try:
            # Wait for fork() process completion
            with fork_lock:
                pass

            # Work only if we've successfully forked
            if self.__pid is not None:
                try:
                    self.__communicate(poll)
                finally:
                    self.__close()

                self.__state = _PROCESS_STATE_TERMINATED
        except Exception:
            LOG.exception("Execution thread crashed.")
        finally:
            poll.close()


    def __ensure_terminated(self):
        """Ensures that the process is terminated."""

        if self.__state != _PROCESS_STATE_TERMINATED:
            raise InvalidProcessState("Process is not terminated")


    def __execute(self, stdout):
        """Executes the command."""

        # Create stdin/stdout/stderr pipes
        for fd in ( psys.STDIN_FILENO, psys.STDOUT_FILENO, psys.STDERR_FILENO ):
            self.__pipes.append(_Pipe(fd, output = bool(fd),
                pipe = stdout if fd == psys.STDOUT_FILENO else None))

        # Execute all processes in the pipe
        if self.__stdin_source is not None:
            for pipe in self.__pipes:
                if pipe.source == psys.STDIN_FILENO:
                    self.__stdin_source._execute(stdout = pipe, check_pipes = False)
                    break
            else:
                raise LogicalError()

        # Fork the process -->
        fork_lock = threading.Lock()

        with fork_lock:
            # Allocate all resources before fork() to guarantee that we will
            # be able to control the process execution.

            # Execution thread -->
            poll = psys.poll.Poll()

            try:
                self.__communication_thread = threading.Thread(
                    target = self.__communication_thread_func,
                    args = [ fork_lock, poll ])

                self.__communication_thread.daemon = True
                self.__communication_thread.start()
            except Exception as e:
                poll.close()
                raise e
            # Execution thread <--

            # Wait thread -->
            try:
                self.__termination_fd, termination_fd = os.pipe()
            except Exception as e:
                raise Error("Unable to create a pipe: {0}.", psys.e(e))

            try:
                self.__wait_thread = threading.Thread(
                    target = self.__wait_pid_thread, args = [ fork_lock, termination_fd ])
                self.__wait_thread.daemon = True
                self.__wait_thread.start()
            except Exception as error:
                try:
                    eintr_retry(os.close)(termination_fd)
                except Exception as e:
                    LOG.error("Unable to close a pipe: %s.", psys.e(e))

                raise error
            # Wait thread <--

            self.__pid = os.fork()

            if self.__pid:
                self.__state = _PROCESS_STATE_RUNNING
            else:
                self.__child()
        # Fork the process <--


    def __join_threads(self, timeout = None):
        """Joins all spawned threads."""

        if timeout is not None:
            end_time = time.time() + timeout

        if not psys.join_thread(self.__wait_thread,
            timeout = None if timeout is None else end_time - time.time()):
            return False

        if not psys.join_thread(self.__communication_thread,
            timeout = None if timeout is None else end_time - time.time()):
            return False

        return True


    def __on_input(self):
        """Called when we are ready to send stdin data to the process."""

        # TODO: convert unicode
        return None


    def __on_output(self, fd, data):
        """Called when we got stdout/stderr data from the process."""

        (self.__stdout if fd == psys.STDOUT_FILENO else self.__stderr).write(data)


    def __or__(self, command):
        """Shell-style pipelines."""

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidProcessState("Process can't be piped after execution")

            if self.__stdout_target is not None:
                raise InvalidOperation("The process' stdout is already redirected")

            command._pipe_process(self)
            self.__stdout_target = command

            return command


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


    def __wait_pid_thread(self, fork_lock, termination_fd):
        """Waits for the process termination."""

        try:
            # Wait for fork() process completion
            with fork_lock:
                pass

            # Wait only if we've successfully forked
            if self.__pid is None:
                return

            try:
                status = eintr_retry(os.waitpid)(self.__pid, 0)[1]
            except Exception as e:
                LOG.error("Failed to waitpid() process %s: %s.", self.__pid, psys.e(e))
                self.__status = 127
            else:
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
                    self.__status = 127
        except Exception:
            LOG.exception("PID waiting thread crashed.")
        finally:
            try:
                eintr_retry(os.close)(termination_fd)
            except Exception as e:
                LOG.error("Unable to close a pipe: %s.", psys.e(e))



class _Pipe():
    """Represents a pipe between two processes."""

    def __init__(self, source, output = True, pipe = None):
        # File descriptor that we are going to replace by this pipe
        self.source = source

        # True if this is output file descriptor
        self.output = output

        if pipe is None:
            try:
                self.read, self.write = os.pipe()
                #print "####", self.read, self.write
            except Exception as e:
                raise Error("Unable to create a pipe: {0}.", psys.e(e))
        else:
            if output:
                self.read = None
                self.write = pipe.write
                pipe.write = None
            else:
                self.read = pipe.read
                pipe.read = None
                self.write = None


    def __del__(self):
        self.close()


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
