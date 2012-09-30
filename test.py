# -*- coding: utf-8 -*-

"""Tests psh module."""

from __future__ import unicode_literals

import pytest

import psh
from psh import sh

try:
    import pycl.log
except ImportError:
    pass
else:
    pycl.log.setup(debug_mode = True)


def test_zero_exit_status():
    """Tests zero exit status."""

    assert sh.true().status() == 0


def test_nonzero_exit_status():
    """Tests nonzero exit status."""

    assert pytest.raises(psh.ExecutionError,
        lambda: sh.false()).value.status() == 1


def test_ok_statuses():
    """Tests _ok_statuses option."""

    assert sh.false(_ok_statuses = [ 0, 1 ] ).status() == 1
    assert pytest.raises(psh.ExecutionError,
        lambda: sh.true(_ok_statuses = [])).value.status() == 0


def test_output():
    """Tests process output handling."""

    valid_stdout = "тест1\nтест3\n"
    valid_stderr = "тест2\nтест4\n"

    command = "echo тест1; echo тест2 >&2; echo тест3; echo тест4 >&2;"

    process = sh.sh("-c", command)
    _check_output(process, valid_stdout, valid_stderr)

    error = pytest.raises(psh.ExecutionError,
        lambda: sh.sh("-c", command + " exit 1")).value
    _check_output(error, valid_stdout, valid_stderr)


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
