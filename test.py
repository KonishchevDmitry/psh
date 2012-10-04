# -*- coding: utf-8 -*-

"""Tests psh module."""

from __future__ import unicode_literals

import os
import platform
import re
import subprocess
import tempfile
import threading

import pytest

import psh
from psh import sh

try:
    import pycl.log
except ImportError:
    pass
else:
    pycl.log.setup(debug_mode = True)


def pytest_funcarg__test(request):
    """Test wrapper that checks the module for leaks."""

    def opened_fds():
        if platform.system() == "Darwin":
            fd_path = "/dev/fd"
        else:
            fd_path = "/proc/self/fd"

        return set( int(fd) for fd in os.listdir(fd_path) )

    def running_threads():
        return set( thread.ident for thread in threading.enumerate() )

    def process_childs():
        process = subprocess.Popen(
            [ "ps", "-A", "-o", "ppid=,pid=,command=" ],
            stdout = subprocess.PIPE)

        stdout, stderr = process.communicate()
        assert not process.returncode
        assert stdout

        return "\n".join(
            line for line in stdout.split("\n")
                if re.search(r"^\s*{pid}\s+(?!{ps_pid})".format(
                    pid = os.getpid(), ps_pid = process.pid), line))

    fds = opened_fds()
    threads = running_threads()
    childs = process_childs()

    def check():
        assert opened_fds() == fds
        assert running_threads() == threads
        assert process_childs() == childs

    request.addfinalizer(check)



def test_command_arguments(test):
    """Tests command argument parsing."""
    # TODO: defer

    process = sh.test(_ok_statuses = [ 0, 1, 2 ])
    assert process.command() == [ "test" ]
    assert process.command_string() == "test"

    process = sh.test(
        b"arg", b"space arg", b"carriage\rline", b"line\narg", b"tab\targ", br"slash\arg", b"quote'arg", b'quote"arg', #b"тест", b"тест тест", # TODO when got rid of subprocess
        "arg", "space arg", "carriage\rline", "line\narg", "tab\targ", r"slash\arg", "quote'arg", 'quote"arg', "тест", "тест тест",
        3, 2 ** 128, 2.0,
        _ok_statuses = [ 0, 1, 2 ]
    )
    assert process.command() == [ "test",
        b"arg", b"space arg", b"carriage\rline", b"line\narg", b"tab\targ", br"slash\arg", b"quote'arg", b'quote"arg',
        "arg", "space arg", "carriage\rline", "line\narg", "tab\targ", r"slash\arg", "quote'arg", 'quote"arg', "тест", "тест тест",
        "3", "340282366920938463463374607431768211456", "2.0"
    ]
    assert process.command_string() == ("test "
        r"""arg 'space arg' 'carriage\rline' 'line\narg' 'tab\targ' 'slash\\arg' "quote'arg" 'quote"arg' """
        r"""arg 'space arg' 'carriage\rline' 'line\narg' 'tab\targ' 'slash\\arg' 'quote\'arg' 'quote"arg' тест 'тест тест' """
        "3 340282366920938463463374607431768211456 2.0"
    )

    process = sh.test("space arg", s = "short_arg", _ok_statuses = [ 0, 1, 2 ])
    assert process.command() == [ "test", "-s", "short_arg", "space arg" ]
    assert process.command_string() == "test -s short_arg 'space arg'"

    process = sh.test("arg", long_long_arg = "long arg", _ok_statuses = [ 0, 1, 2 ])
    assert process.command() == [ "test", "--long-long-arg", "long arg", "arg" ]
    assert process.command_string() == "test --long-long-arg 'long arg' arg"

    process = sh.test("arg", none_arg = None, _ok_statuses = [ 0, 1, 2 ])
    assert process.command() == [ "test", "--none-arg", "arg" ]
    assert process.command_string() == "test --none-arg arg"



def test_zero_exit_status(test):
    """Tests zero exit status."""

    assert sh.true().status() == 0


def test_nonzero_exit_status(test):
    """Tests nonzero exit status."""

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.false()).value.status() == 1


def test_nonexisting_command(test):
    """Tests executing nonexistent."""

    # TODO: more long and complex
    assert pytest.raises(psh.ExecutionError,
        lambda: sh.nonexistent()).value.status() == 127


def test_ok_statuses(test):
    """Tests _ok_statuses option."""

    assert sh.false(_ok_statuses = [ 0, 1 ] ).status() == 1
    assert pytest.raises(psh.ExecutionError,
        lambda: sh.true(_ok_statuses = [])).value.status() == 0



def test_output(test):
    """Tests process output handling."""

    valid_stdout = "тест1\nтест3\n"
    valid_stderr = "тест2\nтест4\n"

    command = "echo тест1; echo тест2 >&2; sleep 1; echo тест3; echo тест4 >&2; "

    process = sh.sh("-c", command)
    _check_output(process, valid_stdout, valid_stderr)

    error = pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", command + " exit 1")).value
    _check_output(error, valid_stdout, valid_stderr)


def test_large_output(test):
    """Tests large amount of output (more than pipe buffer size)."""

    stdout_tempfile = None
    stderr_tempfile = None

    stdout = open("/dev/urandom").read(1024 * 1024)
    stderr = open("/dev/urandom").read(1024 * 1024 + 1)

    try:
        stdout_tempfile = tempfile.NamedTemporaryFile()
        stdout_tempfile.write(stdout)
        stdout_tempfile.flush()

        stderr_tempfile = tempfile.NamedTemporaryFile()
        stderr_tempfile.write(stderr)
        stderr_tempfile.flush()

        process = sh.sh("-c", "cat {stdout} & pid=$!; cat {stderr} >&2; wait $pid;".format(
            stdout = stdout_tempfile.name, stderr = stderr_tempfile.name))

        assert process.raw_stdout() == stdout
        assert process.raw_stderr() == stderr
    finally:
        if stdout_tempfile is not None:
            stdout_tempfile.close()

        if stderr_tempfile is not None:
            stderr_tempfile.close()


def _check_output(obj, valid_stdout, valid_stderr):
    """Checks a program output."""

    stdout = obj.stdout()
    assert type(stdout) == unicode and stdout == valid_stdout

    stderr = obj.stderr()
    assert type(stderr) == unicode and stderr == valid_stderr

    raw_stdout = obj.raw_stdout()
    assert type(raw_stdout) == str and raw_stdout == valid_stdout.encode("utf-8")

    raw_stderr = obj.raw_stderr()
    assert type(raw_stderr) == str and raw_stderr == valid_stderr.encode("utf-8")
