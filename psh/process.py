"""Controls process execution."""

from __future__ import print_function, unicode_literals

from pcore import PY3

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

if PY3:
    from io import BytesIO
    BytesIO = BytesIO # To suppress pyflakes warnings
else:
    from cStringIO import StringIO as BytesIO
    BytesIO = BytesIO # To suppress pyflakes warnings

from pcore import bytes, str

import psys
import psys.poll
from psys import eintr_retry

from psh.exceptions import Error, LogicalError
from psh.exceptions import ExecutionError
from psh.exceptions import InvalidArgument
from psh.exceptions import InvalidOperation
from psh.exceptions import InvalidProcessState
from psh.exceptions import ProcessOutputWasTruncated
from psh._process.output_iterator import OutputIterator
from psh._process.pipe import Pipe

LOG = logging.getLogger(__name__)


class PIPE:
    """A value to configure redirection of stdout/stderr to a pipe."""

class STDIN:
    """A value to disable stdin redirection."""

class STDOUT:
    """
    A value to disable stdout redirection or configure redirection of stderr
    to stdout.
    """

class STDERR:
    """
    A value to disable stderr redirection or configure redirection of stdout
    to stderr.
    """

class File(object):
    """
    A class to configure redirection of stdin/stdout/stderr from/to a file.
    """

    def __init__(self, path, append = False):
        self.path = path
        self.append = append

DEVNULL = File("/dev/null")
"""
A value to configure redirection of stdin/stdout/stderr from/to /dev/null.
"""


_PROCESS_STATE_PENDING = 0
"""Pending process state."""

_PROCESS_STATE_SPAWNING = 1
"""Spawning process state."""

_PROCESS_STATE_RUNNING = 2
"""Running process state."""

_PROCESS_STATE_TERMINATED = 3
"""Terminated process state."""


class Process:
    r"""Represents a process.

    A :py:class:`Process` object doesn't hold any resources (file descriptors,
    threads, etc.) until it is executed. If it's created with ``_defer =
    True`` option (which is default, see :ref:`command-execution`) or executed
    with ``execute()``, all its resources will be freed and the process will
    be waited when :py:class:`Process` instance with ``_defer = True`` option
    will be created or ``execute()`` returns. But if you execute a command in
    other way by ``execute(wait = False)`` or issuing iteration over its
    output (see :ref:`output-iteration`), you should always use ``with``
    context manager to guarantee that the process will be
    :py:meth:`~Process.wait()`'ed and all its resources will be freed when the
    code leaves the ``with`` context - not when Python's garbage collector
    decide to collect the :py:class:`Process` and :py:class:`Process`' output
    iterator objects. You aren't ought to do so, but its very good to do so to
    be sure in your program's behaviour.

    When code leaves a ``with`` context associated with a :py:class:`Process`
    instance, all its output iterators became closed.


    :keyword _defer: if :py:const:`False`, the process will be executed
        automatically in the :py:class:`Process` constructor (see
        :ref:`command-execution`) (default is :py:const:`True`)
    :type _defer: bool


    :keyword _env: overrides the process environment, if :py:const:`None` does
        nothing (default is :py:const:`None`)
    :type _env: :py:class:`dict` or :py:class:`None`


    :keyword _iter_delimiter: separator which will be used as a delimiter for
        process output iteration (see :ref:`output-iteration`) (default is
        "\\n")
    :type _iter_delimiter: :py:class:`str` or :py:class:`unicode`


    :keyword _iter_raw: if :py:const:`True`, output iteration will be on raw
        strings instead of unicode strings (see :ref:`output-iteration`)
        (default is :py:const:`True`)
    :type _iter_raw: bool


    :keyword _ok_statuses: a list of exit status codes that are considered as
        successful (see :ref:`exit-codes`) (default is ``[ 0 ]``)
    :type _ok_statuses: a list of integers


    :keyword _on_execute: if is not :py:const:`None`, the object is called
        before the process execution (default is :py:const:`None`)
    :type _on_execute: :py:class:`collections.Callable`


    :keyword _shell: if True, accept :py:class:`Process` objects as command
        arguments by translating them into a shell script (see
        :ref:`working-with-ssh`) (default is :py:const:`False`)
    :type _shell: bool


    :keyword _stdin: specifies stdin redirection (see :ref:`io-redirection`)
        (default is :py:data:`DEVNULL`)
    :type _stdin: :py:class:`str`, :py:class:`unicode`, :py:const:`STDIN`,
        :py:class:`File`, :py:class:`collections.Iterator`,
        :py:class:`collections.Iterable`


    :keyword _stdout: specifies stdout redirection (see :ref:`io-redirection`)
        (default is :py:const:`PIPE`)
    :type _stdout: :py:const:`PIPE`, :py:class:`File`, :py:const:`STDOUT`,
        :py:const:`STDERR`


    :keyword _stderr: specifies stderr redirection (see :ref:`io-redirection`)
        (default is :py:const:`PIPE`)
    :type _stderr: :py:const:`PIPE`, :py:class:`File`, :py:const:`STDOUT`,
        :py:const:`STDERR`


    :keyword _truncate_output: if ``_wait_for_output = False`` and
        ``_truncate_output = True``, no exception is raised by
        :py:meth:`~Process.execute()` when there is data in stdout or stderr
        after the process termination (default is :py:const:`False`)
    :type _truncate_output: bool


    :keyword _wait_for_output: if ``_stdout = PIPE`` or ``_stderr = PIPE`` and
        ``_wait_for_output = True``, :py:meth:`~Process.execute()` and
        :py:meth:`~Process.wait()` returns only when EOF is gotten on this
        pipes (attention: output iterators always read all data from stdout)
        (default is :py:const:`True`)
    :type _wait_for_output: bool
    """


    __stdin_source = None
    """The process' stdin source (another process, string, etc.)."""

    __stdin_generator = None
    """stdin generator."""

    __stdout_target = PIPE
    """The process' stdout target (another process, stderr, etc.)."""

    __stderr_target = PIPE
    """The process' stderr target (stdout, stderr, etc.)."""


    __wait_for_output = True
    """See _wait_for_output option description."""

    __truncate_output = False
    """See _truncate_output option description."""


    __defer = True
    """See _defer option description."""

    __shell = False
    """See _shell option description."""

    __env = None
    """See _env option description."""


    __iter_raw = False
    """See _iter_raw option description."""

    __iter_delimiter = b"\n"
    """See _iter_delimiter option description."""


    __on_execute = None
    """See _on_execute option description."""


    __error = None
    """Execution error if occurred."""


    def __init__(self, program, *args, **options):
        # Data lock
        self.__lock = threading.Lock()

        # Current state of the process
        self.__state = _PROCESS_STATE_PENDING


        # Program name or full path
        self.__program = program

        # Process' sys.argv
        self.__command = []

        # Success status codes for this command
        self.__ok_statuses = [ os.EX_OK ]


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
        self.__stdout = BytesIO()

        # Process' stderr
        self.__stderr = BytesIO()

        # Process' termination status
        self.__status = None


        # Parse the command arguments
        self.__parse_args(args, options)

        # Execute the process if it is not deferred
        if not self.__defer:
            self.execute()


    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Waits for the process termination and closes the output iterator (if
        created).
        """

        if self.__state >= _PROCESS_STATE_RUNNING:
            self.wait()

        with self.__lock:
            context_objects = self.__context_objects
            self.__context_objects = []

        for obj in context_objects:
            obj = obj()
            if obj is not None:
                obj.close()

        return False


    def __iter__(self):
        """Executes the process and returns an iterator to its output."""

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


    def command(self):
        """Returns command arguments as it will be executed."""

        return self.__command[:]


    def execute(self, wait = True, check_status = True):
        """Executes the command.

        :param wait: if :py:const:`True`, calls ``wait(check_status =
            check_status)`` after process execution.
        :type wait: bool
        """

        self._execute()

        if wait:
            self.wait(check_status = check_status)

        return self


    def kill(self, signal = signal.SIGTERM):
        """Kills the process.

        :param signal: signal which will be used to kill the process.
        :type signal: int

        :returns: :py:const:`True` if the process received the signal (which
            indicates that it's still running).
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
        """
        Returns the process' captured raw stderr (if ``_stderr = PIPE``).
        """

        self.__ensure_terminated()
        return self.__stderr.getvalue()


    def raw_stdout(self):
        """
        Returns the process' captured raw stdout (if ``_stdout = PIPE``).
        """

        self.__ensure_terminated()
        return self.__stdout.getvalue()


    def status(self):
        """Returns the process' exit status."""

        self.__ensure_terminated()
        return self.__status


    def stderr(self):
        """Returns the process' captured stderr (if ``_stderr = PIPE``)."""

        return psys.u(self.raw_stderr())


    def stdout(self):
        """Returns the process' captured stdout (if ``_stdout = PIPE``)."""

        return psys.u(self.raw_stdout())


    def wait(self, check_status = False, kill = None):
        """Waits for the process termination.

        :param check_status: if :py:const:`True`, check the process status
            code (see :ref:`exit-codes`) and other (communication) errors and
            raise an exception if any error occurred.
        :type check_status: bool

        :param kill: if is not :py:const:`None`, kills the process with the
            ``kill(signal = kill)`` and waits for its termination.
        :type kill: int

        :returns: the process exit status
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
                raise ExecutionError(str(self),
                    self.__status, self.raw_stdout(), self.raw_stderr())

        return self.__status


    def _execute(self, stdout = None, check_pipes = True):
        """Executes the command."""

        if self.__on_execute is not None:
            self.__on_execute(self)

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

            if self.__stdin_source not in ( None, STDIN ):
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
                stream.write(b"'" + arg.replace(b"'", b"""'"'"'""") + b"'")
            else:
                stream.write(arg)

        stdin_source = self.__stdin_source

        # Recursively generate a command line for all processes in the pipe
        # (we can't use lock here to prevent deadlocking)
        if isinstance(stdin_source, Process):
            stdin_source._shell_command(stream, pipe_ok_statuses)
            stream.write(b" | ")

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
                    stream.write(b" ")
                write_arg(stream, arg)

            # Stdin redirection
            if isinstance(stdin_source, File):
                stream.write(b" < ")
                write_arg(stream, stdin_source.path)
            elif stdin_source in ( None, STDIN ) or isinstance(stdin_source, Process):
                pass
            elif (
                type(stdin_source) in ( bytes, str ) or
                isinstance(stdin_source, ( collections.Iterator, collections.Iterable ))
            ):
                raise InvalidOperation(
                    "String and iterator input is not supported for serialization to a shell script")
            else:
                raise LogicalError()

            # Stdout redirection
            if self.__piped_to_process() or self.__stdout_target in ( STDOUT, PIPE ):
                pass
            elif self.__stdout_target is STDERR:
                stream.write(b" >&2")
            elif isinstance(self.__stdout_target, File):
                stream.write(b" > ")
                write_arg(stream, self.__stdout_target.path)
            else:
                raise LogicalError()

            # Stderr redirection
            if self.__stderr_target in ( STDERR, PIPE ):
                pass
            elif self.__stderr_target is STDOUT:
                stream.write(b" 2>&1")
            elif isinstance(self.__stderr_target, File):
                stream.write(b" 2> ")
                write_arg(stream, self.__stderr_target.path)
            else:
                raise LogicalError()

            pipe_ok_statuses.append(self.__ok_statuses[:])


    def _shell_command_full(self):
        """
        Generates a shell command which execution is equal to self.execute()
        including handling of errors in the middle of the process pipe.
        """

        command = BytesIO()

        pipe_ok_statuses = []
        self._shell_command(command, pipe_ok_statuses)

        if len(pipe_ok_statuses) == 1:
            return command.getvalue()

        command.write(b"; statuses=(${PIPESTATUS[@]});")

        for process_id, ok_statuses in enumerate(pipe_ok_statuses):
            if process_id == len(pipe_ok_statuses) - 1:
                command.write(psys.b(" exit ${{statuses[{0}]}};".format(process_id)))
            else:
                command.write(psys.b(" case ${{statuses[{0}]}} in".format(process_id)))
                if ok_statuses:
                    command.write(psys.b(" {0});;".format("|".join(str(status) for status in ok_statuses))))
                command.write(b" *) exit 128;; esac;")

        return b"bash -c '" + command.getvalue().replace(b"'", b"""'"'"'""") + b"'"


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
                                path, os.O_WRONLY | os.O_CREAT | ( os.O_APPEND if append else 0 ), 0o666)
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

                # Required when we have C locale
                command = [ psys.b(arg) for arg in self.__command ]

                exec_error = True

                if self.__env is None:
                    os.execvp(self.__program, command)
                else:
                    os.execvpe(self.__program, command, self.__env)
            except Exception as e:
                if exec_error and isinstance(e, EnvironmentError) and e.errno == errno.EACCES:
                    exit_code = 126

                print("Failed to execute '{program}': {error}.".format(
                    program = self.__program, error = psys.e(e)), file = sys.stderr)
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
        poll_objects = 0

        # Configure the poll object and pipes -->
        poll.register(self.__termination_fd, poll.POLLIN)
        poll_objects += 1

        for pipe in self.__pipes:
            fd = pipe.read if pipe.output else pipe.write
            if fd is None:
                continue

            pipe_map[fd] = pipe

            flags = eintr_retry(fcntl.fcntl)(fd, fcntl.F_GETFL)
            eintr_retry(fcntl.fcntl)(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            poll.register(fd, poll.POLLIN if pipe.output else poll.POLLOUT)
            pipe.close(read = not pipe.output, write = pipe.output)
            poll_objects += 1
        # Configure the poll object and pipes <--

        # Communicate with the process -->
        stdin = None

        while poll_objects:
            events = poll.poll()

            for fd, flags in events:
                # Process termination
                if fd == self.__termination_fd:
                    if self.__wait_for_output:
                        poll.unregister(self.__termination_fd)
                        poll_objects -= 1
                        continue
                    else:
                        poll_objects = 0
                        break

                pipe = pipe_map[fd]

                # stdin
                if pipe.source == psys.STDIN_FILENO:
                    if stdin is None:
                        try:
                            stdin = next(self.__stdin_generator)

                            try:
                                if type(stdin) not in ( bytes, str ):
                                    raise TypeError("must be a string")

                                stdin = psys.b(stdin)
                            except Exception as e:
                                raise InvalidArgument("Invalid stdin data: {0}", e)
                        except StopIteration:
                            pass
                        except Exception as e:
                            self.__error = e
                            stdin = None

                    if stdin is None:
                        poll.unregister(fd)
                        poll_objects -= 1
                        pipe.close()
                    else:
                        try:
                            size = eintr_retry(os.write)(fd, stdin)
                        except EnvironmentError as e:
                            # The process closed its stdin
                            if e.errno == errno.EPIPE:
                                poll.unregister(fd)
                                poll_objects -= 1
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
                        poll_objects -= 1
                else:
                    raise LogicalError()
        # Communicate with the process <--

        if not self.__wait_for_output:
            # The process has terminated, but we should continue communication
            # to get output that we haven't got from it yet. But we must do it
            # wisely, because the process might fork() itself, so we'll read
            # its child's output forever.

            # Maximum output size after process termination (bigger than any
            # pipe buffer size).
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
                            if e.errno != errno.EAGAIN:
                                raise e

                            if not self.__truncate_output:
                                self.__error = ProcessOutputWasTruncated(
                                    str(self), self.__status,
                                    self.__stdout.getvalue(), self.__stderr.getvalue())

                            break
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
        except Exception as e:
            LOG.exception("Execution thread crashed.")

            if self.__pid is not None:
                self.__error = e
        finally:
            poll.close()


    def __configure_stdio(self, stdout):
        """Configures the standard I/O file descriptors."""

        # stdin -->
        if self.__stdin_source is None:
            self.__stdin_source = DEVNULL
        elif (
            self.__stdin_source is STDIN or
            isinstance(self.__stdin_source, File)
        ):
            pass
        elif self.__piped_from_process():
            # Connect and execute all processes in the pipe

            pipe = Pipe(psys.STDIN_FILENO, output = False)
            self.__pipes.append(pipe)

            self.__stdin_source._execute(
                stdout = pipe, check_pipes = False)
        else:
            if type(self.__stdin_source) in ( bytes, str ):
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


    def __parse_args(self, args, options):
        """Parses command arguments and options."""

        # Process options -->
        def check_arg(option, value, types = tuple(), instance_of = tuple(), values = tuple()):
            if type(value) not in types and not isinstance(value, instance_of) and value not in values:
                raise InvalidArgument("Invalid value for option {0}", option)

            return value

        for option, value in options.items():
            if not option.startswith("_"):
                continue

            if option == "_defer":
                self.__defer = check_arg(option, value, types = ( bool, ))
            elif option == "_env":
                if value is None:
                    self.__env = value
                else:
                    self.__env = dict(
                        (
                            psys.b(check_arg(option, k, types = ( bytes, str ))),
                            psys.b(check_arg(option, v, types = ( bytes, str )))
                        )
                            for k, v in value.items() )
            elif option == "_iter_delimiter":
                self.__iter_delimiter = psys.b(
                    check_arg(option, value, types = ( bytes, str )))
            elif option == "_iter_raw":
                self.__iter_raw = check_arg(option, value, types = ( bool, ))
            elif option == "_ok_statuses":
                self.__ok_statuses = [
                    check_arg(option, status, types = ( int, )) for status in value ]
            elif option == "_on_execute":
                self.__on_execute = check_arg(option, value, instance_of = collections.Callable)
            elif option == "_shell":
                self.__shell = check_arg(option, value, types = ( bool, ))
            elif option == "_stderr":
                self.__stderr_target = check_arg(
                    option, value, instance_of = File, values = ( STDOUT, STDERR, PIPE ))
            elif option == "_stdin":
                self.__stdin_source = check_arg(option, value, types = ( bytes, str ),
                    instance_of = ( File, collections.Iterator, collections.Iterable ),
                    values = ( STDIN, ))
            elif option == "_stdout":
                self.__stdout_target = check_arg(
                    option, value, instance_of = File, values = ( STDOUT, STDERR, PIPE ))
            elif option == "_truncate_output":
                self.__truncate_output = check_arg(option, value, types = ( bool, ))
            elif option == "_wait_for_output":
                self.__wait_for_output = check_arg(option, value, types = ( bool, ))
            else:
                raise InvalidArgument("Invalid option: {0}", option)
        # Process options <--

        # Command arguments -->
        self.__command.append(self.__program)

        for option, value in options.items():
            if option.startswith("_"):
                pass
            elif len(option) == 1:
                if value is not False:
                    self.__command.append("-" + option)

                    if value is not True:
                        self.__command.append(_get_arg_value(value, self.__shell))
            else:
                if value is not False:
                    self.__command.append("--" + option.replace("_", "-"))

                    if value is not True:
                        self.__command.append(_get_arg_value(value, self.__shell))

        self.__command += [ _get_arg_value(arg, self.__shell) for arg in args ]
        # Command arguments <--


    def __piped_from_process(self):
        """Returns True if this process is piped from another process."""

        return isinstance(self.__stdin_source, Process)


    def __piped_to_process(self):
        """Returns True if this process is piped to another process."""

        return isinstance(self.__stdout_target, Process)


    def __to_bytes(self):
        """Returns the command string.

        .. note::
            Very lazy formatting.
        """

        return psys.b(self.__to_str())


    def __to_str(self):
        """Returns the command string.

        .. note::
            Very lazy formatting.
        """

        command = ""

        for arg in self.__command:
            if command:
                command += " "

            if type(arg) == bytes:
                for c in b""" '"\\\r\n\t""":
                    if c in arg:
                        arg = repr(arg)[1:] if PY3 else repr(arg)
                        break
                else:
                    arg = repr(arg)[1 + int(PY3):-1]

                command += psys.u(arg)
            else:
                for c in """ '"\\\r\n\t""":
                    if c in arg:
                        for replacement in (
                            ( "\\", r"\\" ),
                            ( "'",  r"\'" ),
                            ( "\r", r"\r" ),
                            ( "\n", r"\n" ),
                            ( "\t", r"\t" ),
                        ):
                            arg = arg.replace(*replacement)

                        arg = "'" + arg + "'"
                        break

                command += arg

        return command


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


    if PY3:
        __bytes__ = __to_bytes
        __str__ = __to_str
    else:
        __str__ = __to_bytes
        __unicode__ = __to_str



def _get_arg_value(value, shell):
    """Returns an argument string value."""

    if type(value) in ( bytes, str ):
        return value
    elif type(value) in ( int, float ) + ( tuple() if PY3 else (long,) ):
        return str(value)
    elif shell and isinstance(value, Process):
        return value._shell_command_full()
    else:
        raise InvalidArgument("Invalid argument: command arguments must be basic types only")
