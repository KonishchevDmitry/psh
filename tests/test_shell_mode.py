# -*- coding: utf-8 -*-

"""Tests the shell mode."""

from __future__ import unicode_literals

import logging
import tempfile

import pytest

import psh
import psys
from psh import sh, File, STDOUT, STDERR, DEVNULL

from pcore import PY3
if PY3:
    chr = chr
else:
    chr = unichr

import test
test.init(globals())


def test_execution(test):
    """Tests command execution in the shell mode."""

    process = sh.sh("-c",
        sh.echo("aaa", _stdout=STDERR), _shell=True).execute()
    assert process.stdout() == ""
    assert process.stderr() == "aaa\n"

    process = sh.sh(
        c=sh.sh("-c", "echo aaa >&2", _stderr=STDOUT), _shell=True).execute()
    assert process.stdout() == "aaa\n"
    assert process.stderr() == ""

    process = sh.sh("-c",
        sh.echo("aaa", _stdout=DEVNULL), _shell=True).execute()
    assert process.stdout() == ""
    assert process.stderr() == ""

    pipe = sh.cat() | sh.egrep("bbb|ccc") | sh.grep("ccc")
    process = sh.sh("-c", pipe, _stdin="aaa\nbbb\nccc\n", _shell=True).execute()
    assert process.stdout() == "ccc\n"
    assert process.stderr() == ""


def test_stdout_append_to_file(test, capfd):
    """Tests redirection of stdout to a file with appending."""

    logging.disable(logging.CRITICAL)

    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(b"orig\n")
            temp_file.flush()

            process = sh.sh("-c", sh.sh("-c",
                "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;",
                _stdout=File(temp_file.name, append=True)), _shell=True)
            process.execute()

            assert process.stdout() == ""
            assert process.stderr() == "test2\nтест4\n"

            stdout, stderr = capfd.readouterr()
            assert stdout == ""
            assert stderr == ""

            with open(temp_file.name, "rb") as stdout:
                assert psys.u(stdout.read()) == "orig\ntest1\nтест3\n"
    finally:
        logging.disable(logging.NOTSET)


def test_argument_passing(test):
    """Tests passing data via command line arguments."""

    value = ""
    for i in range(1, 256):
        value += chr(i)

    process = sh.sh("-c", sh.echo(value), _shell=True).execute()
    assert process.stdout() == value + "\n"
    assert process.stderr() == ""


def test_error_codes(test):
    """Tests error codes."""

    sh.sh("-c", sh.true(), _shell=True).execute().status() == 0

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", sh.false(), _shell=True).execute()).value.status() == 1


    pipe = sh.cat() | sh.egrep("bbb|ccc") | sh.grep("ccc")

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", pipe, _stdin="aaa\n", _shell=True).execute()).value.status() == 128

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", pipe, _stdin="bbb\n", _shell=True).execute()).value.status() == 1


def test_disabled_shell_mode(test):
    """
    Tests passing a Process instance to a process which is not in the shell
    mode.
    """

    with pytest.raises(psh.InvalidArgument):
        sh.test(sh.test())

    with pytest.raises(psh.InvalidArgument):
        sh.test(option=sh.test())


def test_unsupported_operations(test):
    """Tests operations that aren't supported in the shell mode."""

    with pytest.raises(psh.InvalidOperation):
        sh.test(sh.test(_stdin="stdin"), _shell=True)

    with pytest.raises(psh.InvalidOperation):
        sh.test(sh.test(_stdin=["stdin"]), _shell=True)

    with pytest.raises(psh.InvalidOperation):
        sh.test(sh.test(_stdin=iter(["stdin"])), _shell=True)
