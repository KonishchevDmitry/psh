# -*- coding: utf-8 -*-

"""Tests process output iteration."""

from __future__ import unicode_literals

import pytest

from pcore import bytes, str

import psh
import psys
from psh import sh

import test
test.init(globals())


def test_output_iteration(test):
    """Tests iteration over process' output."""

    with sh.cat(_stdin = "") as process:
        stdout = [ line for line in process ]
    assert stdout == []


    with sh.cat(_stdin = "aaa\nтест\nbbb") as process:
        stdout = [ line for line in process ]

    assert stdout == [ "aaa\n", "тест\n", "bbb" ]

    for line in stdout:
        assert type(line) == str


def test_output_iteration_with_large_data(test):
    """
    Tests iteration over process' output with large amount of data
    (more than any buffer size).
    """

    stdin = [ str(i) + "\n" for i in range(0, 100000) ]

    with sh.cat(_stdin = "".join(stdin)) as process:
        stdout = [ line for line in process ]

    assert stdout == stdin


def test_output_iteration_with_raw_false(test):
    """Tests iteration over process' output with _iter_raw = False."""

    with sh.cat(_stdin = "aaa\nтест\nbbb", _iter_raw = False) as process:
        stdout = [ line for line in process ]

    assert stdout == [ "aaa\n", "тест\n", "bbb" ]

    for line in stdout:
        assert type(line) == str


def test_output_iteration_with_raw_true(test):
    """Tests iteration over process' output with _iter_raw = True."""

    with sh.cat(_stdin = "aaa\nтест\nbbb", _iter_raw = True) as process:
        stdout = [ line for line in process ]

    assert stdout == [ b"aaa\n", psys.b("тест\n"), b"bbb" ]

    for line in stdout:
        assert type(line) == bytes


def test_output_iteration_option_delimiter(test):
    """Tests iteration over process' output with custom delimiter."""

    with sh.cat(_stdin = "aa\ta\nте\tст\nbbb", _iter_delimiter = "\t") as process:
        stdout = [ line for line in process ]

    assert stdout == [ "aa\t", "a\nте\t", "ст\nbbb" ]


def test_output_iteration_without_delimiter_raw(test):
    """Tests iteration over process' output without delimiter (raw)."""

    with open("/dev/urandom", "rb") as random:
        stdin = random.read(1024 * 1024)

    with sh.cat(_stdin = stdin, _iter_delimiter = "", _iter_raw = True) as process:
        assert stdin == b"".join(block for block in process)


def test_output_iteration_without_delimiter_unicode(test):
    """Tests iteration over process' output without delimiter (unicode)."""

    with pytest.raises(psh.InvalidOperation):
        with sh.echo(_iter_delimiter = "") as process:
            for block in process:
                pass


def test_output_iteration_error(test):
    """Tests iteration over process which returns an error."""

    with sh.grep("aaa", _stdin = "bbb") as process:
        with pytest.raises(psh.ExecutionError):
            for line in process:
                pass


def test_output_iterator_misusing(test):
    """Tests iteration outside 'with' statement."""

    with sh.cat(_stdin = "aaa\nbbb\nccc") as process:
        output = iter(process)
        next(output)

    with pytest.raises(psh.InvalidOperation):
        next(output)
