..  TODO: check all examples

.. py:currentmodule:: psh


psh |version|
=============

psh allows you to spawn new processes in the Unix shell-style way. It is
inspired by `sh <http://amoffat.github.com/sh/>`_ module but has fully
different implementation and API.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc, but it has a very limited language which is often not suitable for
writing complex programs. Python is a very flexible and reach language which is
used in a wide variety of application domains, but its standard
:py:mod:`subprocess` module is very limited. psh combines the power of Python
language and an elegant shell-style way to execute processes.


Examples
--------

Print output of ``echo -n "text"``::

    from psh import sh
    print sh.echo("-n", "text").execute().stdout()


Get a list of all available network interfaces (``ifconfig | egrep -o "^[^[:space:]:]+"``)::

    from psh import sh
    interfaces = [ iface.rstrip("\n") for iface in sh.ifconfig() | sh.egrep("-o", "^[^[:space:]:]+") ]

Check free disk space on remote host *myserver.com*::

    import re
    from psh import sh

    # ssh myserver.com 'df | egrep "^/dev/"'
    with sh.ssh("myserver.com", sh.df() | sh.egrep("^/dev/"), _shell = True) as ssh:
        for line in ssh:
            match = re.search(r"^(/dev/[^\s+]+)\s+(?:[^\s]+\s+){3}(\d+)%\s+(/.*)$", line.rstrip("\n"))
            device, used, mount_point = match.groups()
            if int(used) > 80:
                print "{0} ({1}) ran out of disk space ({2}%)".format(device, mount_point, used)

Output::

    /dev/sda1 (/) ran out of disk space (86%)
    /dev/sda2 (/mnt/data) ran out of disk space (95%)


Installation
------------

You can install psh by executing the following commands in the source
directory::

    python setup.py build
    sudo python setup.py install




Tutorial
========

.. _command-execution:

Command execution
-----------------

:py:mod:`psh` module has an object named :py:data:`sh` which is a factory of
:py:class:`Program` objects. A :py:class:`Program` object represents a program
which can be executed. To obtain a :py:class:`Program` object just write::

    from psh import sh
    echo = sh.echo

For commands that have dashes in their names, for example ``google-chrome``,
substitute the dash for an underscore::

	from psh import sh
	sh.google_chrome("http://google.com")

.. note::

    For commands with more exotic characters in their names, like ``.`` you may
    use :py:meth:`sh.__call__` method::

        from psh import sh

        python = sh("python2.7")
        script = sh("/path/to/script.sh")

To execute a program just call it as if it is a function and then call
:py:meth:`~Process.execute` method::

    sh.echo("text").execute()
    sh("python2.7")("script.py").execute()

``sh.echo("text")`` returns a :py:class:`Process` instance which holds all
arguments and state of the process which will be executed.

Process is not executed automatically by default when :py:class:`Process`
object is created. This is done so to support piping and process output
iteration (see :ref:`piping`, :ref:`output-iteration`). But if you want just
simply run commands, you may use ``_defer = False`` option::

    from psh import sh
    sh.service("httpd", "start", _defer = False)

In this case ``service httpd start`` will be executed immediately and
``sh.service(...)`` call will return only when the process will be terminated.
If you want to always run processes immediately, you may set ``_defer = False``
as default (see :ref:`default-options`).


Keyword arguments
-----------------

Commands support short-form ``-a`` and long-form ``--arg`` arguments as
keyword arguments::

	sh.useradd("ftp", system = True, shell = "/bin/nologin")

which is equal to::

	sh.useradd("--system", "--shell", "/bin/nologin", "ftp")

where both resolve to::

	useradd --system --shell /bin/nologin ftp


.. _piping:

Piping
------

Shell-style piping is performed using :py:class:`Process` object composition.
Just pass one command as the input to another, and psh will create a pipe
between the two::

    process = sh.du() | sh.sort("-nr") | sh.head("-n", 3)
    process.execute()
    process.stdout()

In this case ``process.stdout()`` will return output of ``du | sort -nr | head -n 3``.

.. note::

    You can't execute a pipe as in the following example because of Python's
    evaluation order::

        sh.du() | sh.sort("-nr") | sh.head("-n", 3).execute()

    You may do this by storing a pipe in variable::

        process = sh.du() | sh.sort("-nr") | sh.head("-n", 3)
        process.execute()

    or just::

        ( sh.du() | sh.sort("-nr") | sh.head("-n", 3) ).execute()


I/O redirection
---------------

psh can redirect the standard input, output and error streams::

    # echo text > /dev/null 2>&1
    sh.echo("text", _stdout = psh.DEVNULL, _stderr = psh.STDOUT)

    # echo -n "text" | cat
    sh.echo("text", _stdin = "text")

    # cat < file
    sh.cat("text", _stdin = psh.File("file"))

or even use Python's generators as input::

    # Output: "1\n2\n3\n4\n5\n"
    sh.cat(_stdin = ( str(i) + "\n" for i in xrange(0, 5) )


.. _exit-codes:

Exit codes
----------

Normal processes exit with exit code 0. Process exit code can be obtained
through :py:meth:`~Process.status()`::

    assert sh.true().execute().status() == 0

If a process terminates a nonzero exit code, an exception is raised.

Some programs return nonzero exit codes even though they succeed. If you know
which codes a program might returns and you don't want to deal with doing no-op
exception handling, you can use the ``_ok_statuses`` option::

    sh.mount() | sh.egrep(^/dev/", _ok_statuses = [ 0, 1 ]) | sh.sort()

This means that the ``grep`` command will not generate an exception if the
process exits with 0 or 1 exit code.

.. note::

    Please notice that even if you connect a few processes in a pipe, an
    exception will be raised even if a failed command is not the last command
    in the pipe. This gives you a great power of controlling process execution
    in a very easy way which is not available in the shell.


.. _default-options:

Setting default process options
-------------------------------

As you saw above, you can control process execution via options passed to the
:py:class:`Process` instance, such as ``_defer = False``. But sometimes you may
realize that the default option values is not very suitable for you and you
override them almost in every command.

For example, you want all commands executed immediately saving their original
input and output file descriptors. You can do this by overriding the default
option values for the specific command::

    from psh import Program, STDIN, STDOUT, STDERR

    ssh = Program("ssh", "user@host", _stdin = STDIN, _stdout = STDOUT, _stderr = STDERR, _defer = False)

    # Immediatly executes ``ssh user@host df -h`` preserving the original
    # standart file descriptors.
    ssh("df", "-h")

or you can override them for all commands you execute::

    from psh import Sh, STDIN, STDOUT, STDERR
    sh = Sh(_stdin = STDIN, _stdout = STDOU, _stderr = STDERR, _defer = False)

    sh.ssh("user@host", "df", "-h")


'With' contexts
---------------

You can use ``with`` statement on :py:class:`Process` objects to guarantee that
the process will be wait()'ed when you leave the ``with`` context, which also
frees all opened file descriptors and other resources (see :py:class:`Process`
reference).

Using ``with`` context with :py:class:`Process` objects is the same as with all
other Python's objects::

    from psh import sh

    with sh.mount() as process:
        process.execute(wait = False)
        # do some task here

    # process will be terminated here


.. _output-iteration:

Iterating over output
---------------------

You can iterate over process output as well you do for all Python's file
objects::

    from psh import sh

    with sh.cat("/var/log/messages") as cat:
        for line in cat:
            print line

The process is automatically executed when iteration is initiated.

.. note::

    You should always iterate over process output inside a ``with`` context
    (see :py:class:`Process` for description why).


.. _working-with-ssh:

Working with SSH
----------------

When you need to run a specific command on a remote host you have to run ssh
and pass commands to it as arguments which breaks the all idea of creating and
piping processes with psh. For this reason psh gives you a way to run processes
on a remote host in the same way you use for the local host. The only thing you
have to do is to run shell process (ssh, pdsh, etc) with ``_shell = True``
option and pass a :py:class:`Process` object as an argument to it::

    import re
    from psh import sh

    # ssh myserver.com 'df | egrep "^/dev/"'
    with sh.ssh("myserver.com", sh.df() | sh.egrep("^/dev/"), _shell = True) as ssh:
        for line in ssh:
            match = re.search(r"^(/dev/[^\s+]+)\s+(?:[^\s]+\s+){3}(\d+)%\s+(/.*)$", line.rstrip("\n"))
            device, used, mount_point = match.groups()
            if int(used) > 80:
                print "{0} ({1}) ran out of disk space ({2}%)".format(device, mount_point, used)

When ``_shell = True`` option is passed, all :py:class:`Process` instances that
you specified as arguments will be converted to a shell script, which is equal
to the passed command, and ssh will execute it on the remote side.

For the simple commands the script will be very simple. For example,
``sh.ssh("host", sh.echo("text", _stderr = psh.STDOUT))`` executes ``TODO``,
but for piped commands the script will be more complex. The
``sh.ssh("myserver.com", sh.df() | sh.egrep("^/dev/"), _shell = True)``
executes something like ``TODO``. This complexity is required to detect errors
in processes in the middle of the pipe.

.. note::

    Please note that there is a little difference in executing ::

        sh.echo("data") | sh.grep("text") | sh.wc("-l")

    and ::

        ssh("host", sh.echo("data") | sh.grep("text") | sh.wc("-l"), _shell = True)

    Both commands will raise :py:class:`ExecutionError`, but for the first one
    :py:meth:`ExecutionError.status()` will return 1 from failed ``grep``
    command and for the second one :py:meth:`ExecutionError.status()` will
    return 128.

    This is because there is no way to pass pair "failed command, return status
    code" from within ssh without making the generated script ridiculously
    complex, so all TODO


More info
---------

Please read the :ref:`reference` which explains some important details,
thread-safety guaranties and additional features.
