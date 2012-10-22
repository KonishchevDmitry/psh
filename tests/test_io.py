# -*- coding: utf-8 -*-

"""Tests process input substituting and output capturing."""

from __future__ import unicode_literals

import tempfile

import pytest

from pcore import bytes, str

import psh
import psys
from psh import sh

import test
test.init(globals())


def test_string_input(test):
    """Tests process input from string."""

    assert sh.grep("тест", _stdin = "aaa\nтест\nbbb\n").execute().stdout() == "тест\n"
    assert sh.grep("тест", _stdin = psys.b("aaa\nтест\nbbb\n")).execute().stdout() == "тест\n"


def test_iterator_input(test):
    """Tests process input from string."""

    stdout = "\n".join(str(i) for i in range(0, 10))

    def func():
        for i in range(0, 10):
            yield "\n" + str(i) if i else str(i)

    assert sh.cat(_stdin = func()).execute().stdout() == stdout


def test_file_object_input(test):
    """Tests process input from file object."""

    with tempfile.NamedTemporaryFile() as temp_file:
        with open("/dev/urandom", "rb") as random:
            stdout = random.read(1024 * 1024)

        temp_file.write(stdout)
        temp_file.flush()

        with open(temp_file.name, "rb") as stdin:
            assert sh.cat(_stdin = stdin).execute().raw_stdout() == stdout


def test_invalid_input(test):
    """Tests invalid input."""

    with pytest.raises(psh.InvalidArgument):
        sh.grep(_stdin = 3)

    with pytest.raises(psh.InvalidArgument):
        sh.grep("1", _stdin = iter([ 1 ])).execute()



def test_output(test):
    """Tests process output handling."""

    valid_stdout = "тест1\nтест3\n"
    valid_stderr = "тест2\nтест4\n"

    command = "echo тест1; echo тест2 >&2; sleep 1; echo тест3; echo тест4 >&2; "

    process = sh.sh("-c", command).execute()
    _check_output(process, valid_stdout, valid_stderr)

    error = pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", command + " exit 1").execute()).value
    _check_output(error, valid_stdout, valid_stderr)


def test_large_output(test):
    """Tests large amount of output (more than any pipe buffer size)."""

    stdout_tempfile = None
    stderr_tempfile = None

    with open("/dev/urandom", "rb") as random:
        stdout = random.read(1024 * 1024)
        stderr = random.read(1024 * 1024 + 1)

    try:
        stdout_tempfile = tempfile.NamedTemporaryFile()
        stdout_tempfile.write(stdout)
        stdout_tempfile.flush()

        stderr_tempfile = tempfile.NamedTemporaryFile()
        stderr_tempfile.write(stderr)
        stderr_tempfile.flush()

        process = sh.sh("-c", "cat {stdout} & pid=$!; cat {stderr} >&2; wait $pid;".format(
            stdout = stdout_tempfile.name, stderr = stderr_tempfile.name)).execute()

        assert process.raw_stdout() == stdout
        assert process.raw_stderr() == stderr
    finally:
        if stdout_tempfile is not None:
            stdout_tempfile.close()

        if stderr_tempfile is not None:
            stderr_tempfile.close()


def test_output_after_process_termination(test):
    """Tests execution of a process that terminates before its children."""

    command = [ "-c", "echo aaa; ( sleep 1; echo bbb; )&" ]

    process = sh.sh(*command).execute()
    assert process.status() == 0
    assert process.stdout() == "aaa\nbbb\n"
    assert process.stderr() == ""

    error = pytest.raises(psh.ProcessOutputWasTruncated,
        lambda: sh.sh(*command, _wait_for_output = False).execute()).value
    assert error.status() == 0
    assert error.stdout() == "aaa\n"
    assert error.stderr() == ""

    process = sh.sh(*command, _wait_for_output = False, _truncate_output = True).execute()
    assert process.status() == 0
    assert process.stdout() == "aaa\n"
    assert process.stderr() == ""


def _check_output(obj, valid_stdout, valid_stderr):
    """Checks a program output."""

    stdout = obj.stdout()
    assert type(stdout) == str and stdout == valid_stdout

    stderr = obj.stderr()
    assert type(stderr) == str and stderr == valid_stderr

    raw_stdout = obj.raw_stdout()
    assert type(raw_stdout) == bytes and raw_stdout == psys.b(valid_stdout)

    raw_stderr = obj.raw_stderr()
    assert type(raw_stderr) == bytes and raw_stderr == psys.b(valid_stderr)
