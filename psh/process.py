"""Controls process execution."""

from __future__ import unicode_literals

import cStringIO
import collections
import errno
import fcntl
import logging
import os
import re
import signal
import sys
import threading
import time
import weakref

import psys
import psys.poll
from psys import eintr_retry

from psh.exceptions import Error, LogicalError
from psh.exceptions import ExecutionError
from psh.exceptions import InvalidArgument
from psh.exceptions import InvalidOperation
from psh.exceptions import InvalidProcessState
from psh._process.output_iterator import OutputIterator
from psh._process.pipe import Pipe

LOG = logging.getLogger(__name__)


class PIPE: pass
"""A value to configure redirection of stdout/stderr to a pipe."""

class STDOUT: pass
"""A value to configure redirection of stdout/stderr to stdout."""

class STDERR: pass
"""A value to configure redirection of stdout/stderr to stderr."""

class File(object):
    """A class to configure redirection of stdin/stdout/stderr from/to a file."""

    def __init__(self, path, append = False):
        self.path = path
        self.append = append

DEVNULL = File("/dev/null")
"""A value to configure redirection of stdin/stdout/stderr from/to /dev/null."""


_PROCESS_STATE_PENDING = 0
"""Pending process state."""

_PROCESS_STATE_SPAWNING = 1
"""Spawning process state."""

_PROCESS_STATE_RUNNING = 2
"""Running process state."""

_PROCESS_STATE_TERMINATED = 3
"""Terminated process state."""


class Process:
    """Represents a process."""

    __stdin_source = None
    """The process' stdin source (another process, string, etc.)."""

    __stdin_generator = None
    """stdin generator."""

    __stdout_target = PIPE
    """The process' stdout target (another process, stderr, etc.)."""

    __stderr_target = PIPE
    """The process' stderr target (another process, stdout, etc.)."""


    __shell = False
    """
    If True, accept Process objects as command arguments by translating them
    into a shell script.
    """


    __iter_raw = False
    """
    True if output iteration will be on raw strings instead of unicode
    strings.
    """

    __iter_delimiter = b"\n"
    """
    Separator which will be used as a delimiter for process output
    iteration.
    """


    __error = None
    """Execution error if occurred."""


    def __init__(self, program, *args, **kwargs):
        # Data lock
        self.__lock = threading.Lock()

        # Current state of the process
        self.__state = _PROCESS_STATE_PENDING


        # Program name or full path
        self.__program = program

        # Process' sys.argv
        self.__command = []

        # Success status codes for this command
        self.__ok_statuses = [ psys.EXIT_SUCCESS ]


        # Process' pipes
        self.__pipes = []

        # A pipe to signal about the process termination
        self.__termination_fd = None

        # A thread in which we communicate with the process
        self.__communication_thread = None

        # A thread in which we wait for process termination
        self.__wait_thread = None

        # Objects that must be closed when leaving 'with' context
        self.__context_objects = []


        # PID of the process
        self.__pid = None

        # Process' stdout
        self.__stdout = cStringIO.StringIO()

        # Process' stderr
        self.__stderr = cStringIO.StringIO()

        # Process' termination status
        self.__status = None


        # Parse the command arguments
        self.__parse_args(args, kwargs)


    def __enter__(self):
        """
        'with' operator guarantees that the process will be wait()'ed and the
        output iterator will be closed (if created).
        """

        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        """Waits for the process termination."""

        with self.__lock:
            context_objects = self.__context_objects
            self.__context_objects = []

        for obj in context_objects:
            obj = obj()
            if obj is not None:
                obj.close()

        if self.__state >= _PROCESS_STATE_RUNNING:
            self.wait()

        return False


    def __iter__(self):
        """Executes the process and returns a line iterator to its output."""

        iterator = OutputIterator(
            self, self.__iter_raw, self.__iter_delimiter)

        try:
            self._execute(stdout = iterator.pipe())

            with self.__lock:
                self.__context_objects.append(weakref.ref(iterator))
        except:
            iterator.close()
            raise

        return iterator


    def __or__(self, process):
        """Shell-style pipelines."""

        if not isinstance(process, Process):
            raise InvalidOperation("Process may be piped only with another process")

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidProcessState("Process can't be piped after execution")

            if self.__stdout_target is not PIPE:
                raise InvalidOperation("The process' stdout is already redirected")

            orig_stdout_target = self.__stdout_target
            self.__stdout_target = process

        try:
            # Must be outside the lock to prevent deadlocking
            process._pipe_process(self)
        except:
            with self.__lock:
                self.__stdout_target = orig_stdout_target
            raise

        return process


    def __str__(self):
        """Returns the command string.

        Note: very lazy formatting.
        """

        return psys.b(self.__unicode__())


    def __unicode__(self):
        """Returns the command string.

        Note: very lazy formatting.
        """

        command = ""

        for arg in self.__command:
            if command:
                command += " "

            if type(arg) == str:
                for c in b""" '"\\\r\n\t""":
                    if c in arg:
                        arg = repr(arg)
                        break
                else:
                    arg = repr(arg)[1:-1]

                command += psys.u(arg)
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


    def command(self):
        """Returns command arguments as it will be executed."""

        return self.__command[:]


    def execute(self, check_status = True, wait = True):
        """Executes the command."""

        self._execute()

        if wait:
            self.wait(check_status = check_status)

        return self


    def kill(self, signal = signal.SIGTERM):
        """Kills the process.

        Returns True if the process received the signal.
        """

        if self.__state < _PROCESS_STATE_RUNNING:
            raise InvalidProcessState("Process is not running")

        if self.__state == _PROCESS_STATE_RUNNING:
            LOG.debug("Send %s signal to %s...", signal, self)

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

        LOG.debug("Waiting for %s termination%s...",
            self, "" if kill is None else " killing it with {0} signal".format(kill))

        if kill is not None:
            while self.kill(kill):
                if self.__join_threads(0.1):
                    break

        self.__join_threads()

        if self.__piped_from_process():
            self.__stdin_source.wait(
                check_status = check_status, kill = kill)

        if check_status:
            if self.__error is not None:
                raise self.__error

            if self.__status not in self.__ok_statuses:
                raise ExecutionError(self.__status, self.raw_stdout(), self.raw_stderr())

        return self.__status


    def _execute(self, stdout = None, check_pipes = True):
        """Executes the command."""

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidOperation("The process has been executed already")

            if check_pipes and self.__piped_to_process():
                raise InvalidOperation("Only the last process of the pipe can be executed")

            self.__state = _PROCESS_STATE_SPAWNING

        LOG.debug("Executing %s", self)

        try:
            self.__execute(stdout)
        except:
            self.__close()
            self.__join_threads()

            if (
                self.__piped_from_process() and
                self.__stdin_source._state() >= _PROCESS_STATE_RUNNING
            ):
                self.__stdin_source.wait(kill = signal.SIGTERM)

            raise


    def _pipe_process(self, process):
        """Creates a pipe between two processes."""

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidProcessState("Process can't be piped after execution")

            if self.__stdin_source is not None:
                raise InvalidOperation("The process' stdin is already redirected")

            LOG.debug("Creating a pipe: %s | %s", process, self)
            self.__stdin_source = process


    def _shell_command(self, stream, pipe_ok_statuses):
        """
        Generates a shell command which execution is equal to
        self.execute().
        """

        simple_arg_re = re.compile(b"^[-a-zA-Z0-9/_.:=+]+$")

        def write_arg(stream, arg):
            arg = psys.b(arg)

            if simple_arg_re.search(arg) is None:
                stream.write(b"'" + arg.replace(b"'", """'"'"'""") + b"'")
            else:
                stream.write(arg)

        stdin_source = self.__stdin_source

        # Recursively generate a command line for all processes in the pipe
        # (we can't use lock here to prevent deadlocking)
        if isinstance(stdin_source, Process):
            stdin_source._shell_command(stream, pipe_ok_statuses)
            stream.write(" | ")

        with self.__lock:
            # Just in case. Actually, at this time we don't need to lock and
            # check state here - it's enough to copy all objects to local
            # variables, but in the future it may be necessary to create a
            # consistent command line.
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidProcessState(
                    "The command can't be serialized to a shell script after it's execution")

            # Command arguments
            for arg_id, arg in enumerate(self.__command):
                if arg_id:
                    stream.write(" ")
                write_arg(stream, arg)

            # Stdin redirection
            if isinstance(stdin_source, File):
                stream.write(" < ")
                write_arg(stream, stdin_source.path)
            elif stdin_source is None or isinstance(stdin_source, Process):
                pass
            elif isinstance(stdin_source, ( basestring, collections.Iterator, collections.Iterable )):
                raise InvalidOperation(
                    "String and iterator input is not supported for serialization to a shell script")
            else:
                raise LogicalError()

            # Stdout redirection
            if self.__piped_to_process() or self.__stdout_target in ( STDOUT, PIPE ):
                pass
            elif self.__stdout_target is STDERR:
                stream.write(" >&2")
            elif isinstance(self.__stdout_target, File):
                stream.write(" > ")
                write_arg(stream, self.__stdout_target.path)
            else:
                raise LogicalError()

            # Stderr redirection
            if self.__stderr_target in ( STDERR, PIPE ):
                pass
            elif self.__stderr_target is STDOUT:
                stream.write(" 2>&1")
            elif isinstance(self.__stderr_target, File):
                stream.write(" 2> ")
                write_arg(stream, self.__stderr_target.path)
            else:
                raise LogicalError()

            pipe_ok_statuses.append(self.__ok_statuses[:])


    def _shell_command_full(self):
        """
        Generates a shell command which execution is equal to self.execute()
        including handling of errors in the middle of the process pipe.
        """

        command = cStringIO.StringIO()

        pipe_ok_statuses = []
        self._shell_command(command, pipe_ok_statuses)

        if len(pipe_ok_statuses) == 1:
            return command.getvalue()

        command.write("; statuses=(${PIPESTATUS[@]});")

        for process_id, ok_statuses in enumerate(pipe_ok_statuses):
            if process_id == len(pipe_ok_statuses) - 1:
                command.write(" exit ${{statuses[{0}]}};".format(process_id))
            else:
                command.write(" case ${{statuses[{0}]}} in".format(process_id))
                if ok_statuses:
                    command.write(" {0});;".format("|".join(str(status) for status in ok_statuses)))
                command.write(" *) exit 128;; esac;".format(process_id))

        return b"bash -c '" + command.getvalue().replace(b"'", """'"'"'""") + b"'"


    def _state(self):
        """Returns current process state."""

        return self.__state


    def __child(self):
        """Handles child process execution."""

        exit_code = 127

        try:
            exec_error = False

            try:
                fd_name = {
                    0: "stdin",
                    1: "stdout",
                    2: "stderr",
                }

                def redirect_fd(path, fd, write = True, append = False):
                    try:
                        if write:
                            file_fd = eintr_retry(os.open)(
                                path, os.O_WRONLY | os.O_CREAT | ( os.O_APPEND if append else 0 ), 0666)
                        else:
                            file_fd = eintr_retry(os.open)(path, os.O_RDONLY)

                        try:
                            eintr_retry(os.dup2)(file_fd, fd)
                        finally:
                            eintr_retry(os.close)(file_fd)
                    except Exception as e:
                        raise Error("Unable to redirect {0} to {1}: {2}",
                            fd_name[fd] if write else "'" + path + "'",
                            "'" + path + "'" if write else fd_name[fd], psys.e(e))

                # Connect all pipes
                for pipe in self.__pipes:
                    try:
                        eintr_retry(os.dup2)(pipe.write if pipe.output else pipe.read, pipe.source)
                    except Exception as e:
                        raise Error("Unable to connect a pipe to {0}: {1}",
                            fd_name[pipe.source], psys.e(e))

                    pipe.close()

                # Close all file descriptors
                psys.close_all_fds()

                # Configure stdin
                if isinstance(self.__stdin_source, File):
                    redirect_fd(self.__stdin_source.path, psys.STDIN_FILENO, write = False)

                # Configure stdout
                if self.__stdout_target is STDERR:
                    try:
                        eintr_retry(os.dup2)(psys.STDERR_FILENO, psys.STDOUT_FILENO)
                    except Exception as e:
                        raise Error("Unable to redirect stderr to stdout: {0}", psys.e(e))
                elif isinstance(self.__stdout_target, File):
                    redirect_fd(self.__stdout_target.path, psys.STDOUT_FILENO,
                        append = self.__stdout_target.append)

                # Configure stderr
                if self.__stderr_target is STDOUT:
                    try:
                        eintr_retry(os.dup2)(psys.STDOUT_FILENO, psys.STDERR_FILENO)
                    except Exception as e:
                        raise Error("Unable to redirect stderr to stdout: {0}", psys.e(e))
                elif isinstance(self.__stderr_target, File):
                    redirect_fd(self.__stderr_target.path, psys.STDERR_FILENO,
                        append = self.__stderr_target.append)

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
            # TODO: read all
            for fd, flags in poll.poll():
                # Process termination
                if fd == self.__termination_fd:
                    terminated = True
                    break

                pipe = pipe_map[fd]

                # stdin
                if pipe.source == psys.STDIN_FILENO:
                    if stdin is None:
                        try:
                            stdin = next(self.__stdin_generator)

                            try:
                                if isinstance(stdin, unicode):
                                    stdin = psys.b(stdin)
                                elif not isinstance(stdin, str):
                                    raise ValueError("must be a string")
                            except Exception as e:
                                raise InvalidArgument("Invalid stdin data: {0}", e)
                        except StopIteration:
                            pass
                        except Exception as e:
                            self.__error = e
                            stdin = None

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


    def __configure_stdio(self, stdout):
        """Configures the standard I/O file descriptors."""

        # stdin -->
        if self.__stdin_source is None:
            self.__stdin_source = DEVNULL
        elif isinstance(self.__stdin_source, File):
            pass
        elif self.__piped_from_process():
            # Connect and execute all processes in the pipe

            pipe = Pipe(psys.STDIN_FILENO, output = False)
            self.__pipes.append(pipe)

            self.__stdin_source._execute(
                stdout = pipe, check_pipes = False)
        else:
            if isinstance(self.__stdin_source, basestring):
                self.__stdin_generator = iter([ self.__stdin_source ])
            elif isinstance(self.__stdin_source, collections.Iterator):
                self.__stdin_generator = self.__stdin_source
            elif isinstance(self.__stdin_source, collections.Iterable):
                self.__stdin_generator = iter(self.__stdin_source)
            else:
                raise LogicalError()

            pipe = Pipe(psys.STDIN_FILENO, output = False)
            self.__pipes.append(pipe)
        # stdin <--

        # stdout -->
        if self.__stdout_target in ( STDOUT, STDERR ) or isinstance(self.__stdout_target, File):
            if stdout is not None:
                raise LogicalError()
        elif self.__stdout_target is PIPE or self.__piped_to_process():
            self.__pipes.append(Pipe(psys.STDOUT_FILENO, pipe = stdout))
        else:
            raise LogicalError()
        # stdout <--

        # stderr -->
        if self.__stderr_target in ( STDOUT, STDERR ) or isinstance(self.__stderr_target, File):
            pass
        elif self.__stderr_target is PIPE:
            self.__pipes.append(Pipe(psys.STDERR_FILENO))
        else:
            raise LogicalError()
        # stdout <--


    def __ensure_terminated(self):
        """Ensures that the process is terminated."""

        if self.__state != _PROCESS_STATE_TERMINATED:
            raise InvalidProcessState("The process is not terminated")


    def __execute(self, stdout):
        """Executes the command."""

        # Configure the standard I/O file descriptors
        self.__configure_stdio(stdout)

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
            except:
                poll.close()
                raise
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
            except BaseException as error:
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


    def __on_output(self, fd, data):
        """Called when we got stdout/stderr data from the process."""

        (self.__stdout if fd == psys.STDOUT_FILENO else self.__stderr).write(data)


    def __parse_args(self, args, kwargs):
        """Parses command arguments and options."""

        def check_arg(option, value, types = tuple(), values = []):
            if not isinstance(value, types) and value not in values:
                raise InvalidArgument("Invalid value type for option {0}", option)

            return value

        self.__command.append(self.__program)

        if "_shell" in kwargs:
            self.__shell = check_arg("_shell", kwargs["_shell"], bool)

        for option, value in kwargs.iteritems():
            if option.startswith("_"):
                if option == "_iter_delimiter":
                    check_arg(option, value, basestring)
                    if isinstance(value, unicode):
                        value = psys.b(value)
                    self.__iter_delimiter = value
                elif option == "_iter_raw":
                    self.__iter_raw = check_arg(option, value, bool)
                elif option == "_ok_statuses":
                    self.__ok_statuses = [ int(status) for status in value ]
                elif option == "_shell":
                    pass
                elif option == "_stderr":
                    self.__stderr_target = check_arg(
                        option, value, types = File, values = ( STDOUT, STDERR ))
                elif option == "_stdin":
                    self.__stdin_source = check_arg(option, value,
                        ( str, unicode, File, collections.Iterator, collections.Iterable ))
                elif option == "_stdout":
                    self.__stdout_target = check_arg(
                        option, value, types = File, values = ( STDOUT, STDERR ))
                else:
                    raise InvalidArgument("Invalid option: {0}", option)
            elif len(option) == 1:
                self.__command.append("-" + option)
                if value is not None:
                    self.__command.append(_get_arg_value(value, self.__shell))
            else:
                self.__command.append("--" + option.replace("_", "-"))
                if value is not None:
                    self.__command.append(_get_arg_value(value, self.__shell))

        self.__command += [ _get_arg_value(arg, self.__shell) for arg in args ]


    def __piped_from_process(self):
        """Returns True if this process is piped from another process."""

        return isinstance(self.__stdin_source, Process)


    def __piped_to_process(self):
        """Returns True if this process is piped to another process."""

        return isinstance(self.__stdout_target, Process)


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
                    LOG.debug("Command %s terminated with %s status code.", self, self.__status)
                elif os.WIFSIGNALED(status):
                    signum = os.WTERMSIG(status)
                    LOG.debug("Command %s terminated due to receipt of %s signal.", self, signum)
                    self.__status = 128 + signum
                else:
                    LOG.error("Command %s terminated due to unknown reason.", self)
                    self.__status = 127
        except Exception:
            LOG.exception("PID waiting thread crashed.")
        finally:
            try:
                eintr_retry(os.close)(termination_fd)
            except Exception as e:
                LOG.error("Unable to close a pipe: %s.", psys.e(e))



def _get_arg_value(value, shell):
    """Returns an argument string value."""

    if type(value) in ( str, unicode ):
        return value
    elif type(value) in ( int, long, float ):
        return unicode(value)
    elif shell and isinstance(value, Process):
        return value._shell_command_full()
    else:
        raise InvalidArgument("Invalid argument: command arguments must be basic types only")
