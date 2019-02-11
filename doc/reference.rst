.. py:currentmodule:: psh

.. _reference:

Module reference
================

.. toctree::
    :hidden:

    intro


Thread-safety
-------------

All module's objects are thread-safe with the following exception: process
output iterators (see :ref:`output-iteration`) are not thread-safe. You mustn't
use the same output iterator from different threads simultaneously. In other
case it leads to unexpected results. You also mustn't use ``with`` contexts
simultaneously from different threads on the same :py:class:`Process` object,
because when one thread leaves ``with`` context it invalidates an output
iterator from another thread which is not thread-safe.


Module objects
--------------

.. automodule:: psh
    :members: Sh, Program, Process, STDIN, STDOUT, STDERR, PIPE, File, DEVNULL
    :special-members:
    :exclude-members: __weakref__

.. autodata:: psh.DEVNULL


Exceptions
----------

.. autoexception:: Error
    :members:

.. autoexception:: ExecutionError
    :members:

.. autoexception:: InvalidArgument
    :members:

.. autoexception:: InvalidOperation
    :members:

.. autoexception:: InvalidProcessState
    :members:

.. autoexception:: ProcessOutputWasTruncated
    :members:
