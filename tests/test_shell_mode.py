# -*- coding: utf-8 -*-

"""Tests the shell mode."""

from __future__ import unicode_literals

import pytest

import psh
from psh import sh, STDOUT, STDERR, DEVNULL

import test
test.init(globals())


def test_execution(test):
    """Tests command execution in the shell mode."""

    process = sh.sh("-c",
        sh.echo("aaa", _stdout = STDERR), _shell = True).execute()
    process.stdout() == ""
    process.stderr() == "aaa\n"

    process = sh.sh(
        c = sh.sh("-c", "echo aaa >&2", _stderr = STDOUT), _shell = True).execute()
    process.stdout() == "aaa\n"
    process.stderr() == ""

    process = sh.sh("-c",
        sh.echo("aaa", _stdout = DEVNULL), _shell = True).execute()
    process.stdout() == ""
    process.stderr() == ""


    pipe = sh.cat() | sh.egrep("bbb|ccc") | sh.grep("ccc")

    process = sh.sh("-c", pipe, _stdin = "aaa\nbbb\nccc\n", _shell = True).execute()
    process.stdout() == "bbb\n"
    process.stderr() == ""


def test_error_codes(test):
    """Tests error codes."""

    sh.sh("-c", sh.true(), _shell = True).execute().status() == 0

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", sh.false(), _shell = True).execute()).value.status() == 1


    pipe = sh.cat() | sh.egrep("bbb|ccc") | sh.grep("ccc")

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", pipe, _stdin = "aaa\n", _shell = True).execute()).value.status() == 128

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", pipe, _stdin = "bbb\n", _shell = True).execute()).value.status() == 1


def test_disabled_shell_mode(test):
    """
    Tests passing a Process instance to a process which is not in the shell
    mode.
    """

    with pytest.raises(psh.InvalidArgument):
        sh.test(sh.test())

    with pytest.raises(psh.InvalidArgument):
        sh.test(option = sh.test())


def test_unsupported_operations(test):
    """Tests operations that aren't supported in the shell mode."""

    with pytest.raises(psh.InvalidOperation):
        sh.test(sh.test(_stdin = "stdin"), _shell = True)

    with pytest.raises(psh.InvalidOperation):
        sh.test(sh.test(_stdin = [ "stdin" ]), _shell = True)

    with pytest.raises(psh.InvalidOperation):
        sh.test(sh.test(_stdin = iter([ "stdin" ] )), _shell = True)
