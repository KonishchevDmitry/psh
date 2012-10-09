"""Process management library.

Notes:

Process object doesn't hold any resources (file descriptors, etc.) until it
executed. If it executed with execute(wait = True), all its resources will be
freed and the process will be waited when execute() returns. But if you
execute a command in other way (by execute(wait = False) or issuing iteration
over its output) you should use 'with' context manager to guarantee that the
process will be terminated and all its resources will be freed (see below).
You aren't ought to do so, but its very good to do so to be sure in your
program behaviour.

You can use 'with' statement on Process objects to guarantee that the process
will be wait()'ed when you leave the 'with' context (which is also frees all
opened file descriptors and other resources).

If you iterate over process output, you should do it within 'with' context to
guarantee that all opened file descriptors will be closed as soon as you end
iteration or leave the 'with' context. Otherwise they will be closed only when
Python's garbage collector consider to destroy the output iterator.

When code leaves a 'with' context associated with a Process instance, all its
output iterators became closed.

All library's objects are thread-safe with the following exception: Process
output iterators are not thread-safe. You mustn't use the same output iterator
from different threads simultaneously. In other case it leads to unexpected
results. According to said above you also mustn't use 'with' contexts
simultaneously from different threads on the same process, because when one
thread leave 'with' context it will invalidate an output iterator from another
thread which is not thread-safe.
"""

from __future__ import unicode_literals

import psh.process


class Sh(object):
    """An object that allows to run commands in the shell-style way."""

    def __getattribute__(self, attr):
        """Creates a Program instance."""

        return Program(attr)


    def __call__(self, program):
        """Creates a Program instance."""

        return Program(program)


class Program:
    """Represents a program."""

    def __init__(self, program):
        # Program name or full path
        self.__program = program


    def __call__(self, *args, **kwargs):
        """Creates a Process instance from Program instance."""

        return psh.process.Process(self.__program, *args, **kwargs)


from psh.exceptions import Error, ExecutionError, InvalidArgument, InvalidOperation, InvalidProcessState
from psh.process import File, STDOUT, STDERR, DEVNULL

sh = Sh()
