# -*- coding: utf-8 -*-

"""Tests process piping."""

from __future__ import unicode_literals

import pytest

import psh
from psh import sh

import test
test.init(globals())


def test_pipes(test):
    """Tests process pipes."""

    process = sh.cat(_stdin = "aaaa\nbbbb\n" * 1024 * 100) | sh.grep("aaaa") | sh.wc("-l")
    assert process.execute().stdout().strip() == "102400"


def test_abandoned_pipe(test):
    """Tests that an abandoned pipe doesn't lead to resource leaks."""

    sh.cat("/etc/fstab") | sh.grep("/dev") | sh.wc("-l")


def test_pipe_errors(test):
    """Tests errors in the middle of the pipe."""

    process = sh.echo("aaa") | sh.grep("bbb") | sh.wc("-l")
    assert pytest.raises(psh.ExecutionError,
        lambda: process.execute()).value.status() == 1

    process = sh.echo("aaa") | sh.grep("bbb", _ok_statuses = [ 0, 1 ]) | sh.wc("-l")
    process.execute().stdout().strip() == "0"


def test_piping_errors(test):
    """Tests invalid process piping."""

    process = sh.cat()
    with pytest.raises(psh.InvalidOperation):
        process | "string"

    process = sh.cat()
    process | sh.grep()
    with pytest.raises(psh.InvalidOperation):
        process | sh.grep()

    process = sh.cat()
    process | sh.grep()
    with pytest.raises(psh.InvalidOperation):
        process.execute()
