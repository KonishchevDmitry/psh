"""Controls command executing."""

from __future__ import unicode_literals

import cStringIO
import collections
import errno
import fcntl
import logging
import os
import signal
import sys
import threading
import time
import weakref

import psys
import psys.poll
from psys import eintr_retry

import psh
from psh.exceptions import Error, LogicalError
from psh.exceptions import ExecutionError
from psh.exceptions import InvalidArgument
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


# TODO: thread safety guaranties
# If you iterate over process output you should do it within 'with' context to
# guarantee that all opened file descriptors will be closed as soon as you end
# iteration or leave the 'with' context. Otherwise they will be closed only
# when Python's garbage collector consider to destroy them.
#
# If the process 
class Command:
    """Represents an executing command."""

    __stdin_source = None
    """
    The process' custom stdin source (another process, string or
    generator).
    """

    __stdin_generator = None
    """stdin generator."""

    __stdout_target = None
    """The process' custom stdout target (another process)."""


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

        # Command's sys.argv
        self.__command = []

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

        # Objects that must be closed when leaving 'with' context
        self.__context_objects = []


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

        iterator = _OutputIterator(
            self, self.__iter_raw, self.__iter_delimiter)

        try:
            self._execute(stdout = iterator.pipe())

            with self.__lock:
                self.__context_objects.append(weakref.ref(iterator))
        except:
            iterator.close()
            raise

        return iterator


    def __or__(self, command):
        """Shell-style pipelines."""

        if not isinstance(command, Command):
            raise InvalidOperation("Process may be piped only with another process")

        with self.__lock:
            if self.__state != _PROCESS_STATE_PENDING:
                raise InvalidProcessState("Process can't be piped after execution")

            if self.__stdout_target is not None:
                raise InvalidOperation("The process' stdout is already redirected")

            command._pipe_process(self)
            self.__stdout_target = command

            return command


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

            if check_pipes and self.__stdout_target is not None:
                raise InvalidOperation("Only the last process of the pipe can be executed")

            self.__state = _PROCESS_STATE_SPAWNING

        LOG.debug("Executing %s", self.command_string())

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

        # Configure stdin -->
        if self.__stdin_source is None:
            self.__stdin_generator = iter([])
        elif self.__piped_from_process():
            # Execute all processes in the pipe

            for pipe in self.__pipes:
                if pipe.source == psys.STDIN_FILENO:
                    self.__stdin_source._execute(
                        stdout = pipe, check_pipes = False)
                    break
            else:
                raise LogicalError()
        elif isinstance(self.__stdin_source, basestring):
            self.__stdin_generator = iter([ self.__stdin_source ])
        elif isinstance(self.__stdin_source, collections.Iterator):
            self.__stdin_generator = self.__stdin_source
        else:
            raise LogicalError()
        # Configure stdin <--

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

        def check_arg_type(option, value, types):
            if not isinstance(value, types):
                raise InvalidArgument("Invalid value type for option {0}", option)

        self.__command.append(self.__program)

        for option, value in kwargs.iteritems():
            if option.startswith("_"):
                if option == "_iter_delimiter":
                    check_arg_type(option, value, basestring)
                    if isinstance(value, unicode):
                        value = psys.b(value)
                    self.__iter_delimiter = value
                elif option == "_iter_raw":
                    check_arg_type(option, value, bool)
                    self.__iter_raw = value
                elif option == "_ok_statuses":
                    self.__ok_statuses = [ int(status) for status in value ]
                elif option == "_stdin":
                    check_arg_type(option, value, ( str, unicode, collections.Iterator ))
                    self.__stdin_source = value
                else:
                    raise InvalidArgument("Invalid option: {0}", option)
            elif len(option) == 1:
                self.__command.append("-" + option)
                if value is not None:
                    self.__command.append(_get_arg_value(value))
            else:
                self.__command.append("--" + option.replace("_", "-"))
                if value is not None:
                    self.__command.append(_get_arg_value(value))

        self.__command += [ _get_arg_value(arg) for arg in args ]


    def __piped_from_process(self):
        """Returns True if this process is piped from another process."""

        return self.__stdin_source is not None and isinstance(self.__stdin_source, Command)


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



# TODO: read all or not
class _OutputIterator:
    """Process output iterator."""

    def __init__(self, process, raw, delimiter):
        # The process
        self.__process = process

        # Raw or unicode string iteration
        self.__raw = raw

        # Block delimiter
        self.__delimiter = delimiter

        # Output pipe
        self.__pipe = None

        # Polling object
        self.__poll = None

        # Output data buffer. None indicates EOF.
        self.__data = b""

        # Is the iterator closed
        self.__closed = False

        if delimiter:
            self.__iter = self.__iter_with_delimiter
        else:
            if raw:
                self.__iter = self.__iter_without_delimiter
            else:
                raise InvalidOperation("Can't iterate over unicode data without delimiter")

        try:
            self.__pipe = _Pipe(psys.STDOUT_FILENO)
            flags = eintr_retry(fcntl.fcntl)(self.__pipe.read, fcntl.F_GETFL)
            eintr_retry(fcntl.fcntl)(self.__pipe.read, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self.__poll = psys.poll.Poll()
            self.__poll.register(self.__pipe.read, self.__poll.POLLIN)
        except:
            self.close()
            raise


    def __del__(self):
        # Don't close the object in unit tests to be able to detect leaks
        if not hasattr(psh, "_UNIT_TEST"):
            self.close()


    def close(self):
        """Closes the iterator."""

        if self.__closed:
            return

        if self.__poll is not None:
            self.__poll.close()

        if self.__pipe is not None:
            self.__pipe.close()

        self.__closed = True


    def next(self):
        """Iterator's 'next' method."""

        if self.__data is None:
            raise StopIteration()

        if self.__closed:
            raise InvalidOperation("The iterator is closed")

        return self.__iter()


    def pipe(self):
        """Returns the output pipe."""

        return self.__pipe


    def __finalize(self, check_status = True):
        """Finalizes the iterator (on error or when we read all data)."""

        self.close()
        self.__process.wait(check_status)


    def __iter_with_delimiter(self):
        """Iterates over the data splitting it with the delimiter."""

        try:
            pos = self.__data.index(self.__delimiter)
        except ValueError:
            while True:
                try:
                    self.__poll.poll()
                    data = eintr_retry(os.read)(self.__pipe.read, psys.BUFSIZE)
                except:
                    self.__finalize(check_status = False)
                    raise

                if data:
                    try:
                        pos = data.index(self.__delimiter)
                    except ValueError:
                        self.__data += data
                    else:
                        block = self.__data + data[:pos + 1]
                        self.__data = data[pos + 1:]
                        return self.__transform_block(block)
                else:
                    block = self.__data
                    self.__data = None
                    self.__finalize()

                    if not block:
                        raise StopIteration()

                    return self.__transform_block(block)
        else:
            block = self.__data[:pos + 1]
            self.__data = self.__data[pos + 1:]
            return self.__transform_block(block)


    def __iter_without_delimiter(self):
        """Iterates over the data."""

        try:
            self.__poll.poll()
            data = eintr_retry(os.read)(self.__pipe.read, psys.BUFSIZE)
        except:
            self.__finalize()
            raise
        else:
            if not data:
                self.__data = None
                raise StopIteration()

            return data


    def __transform_block(self, block):
        """Transforms the data block to the output format."""

        if self.__raw:
            return block
        else:
            try:
                return psys.u(block)
            except:
                self.__finalize()
                raise


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
        # Don't close the object in unit tests to be able to detect leaks
        if not hasattr(psh, "_UNIT_TEST"):
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
        raise InvalidArgument("Invalid argument: command arguments must be basic types only")
