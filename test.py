#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests psh module."""

from __future__ import unicode_literals

# TODO: test unicode

# TODO
import pytest
import psh
import pycl.log
pycl.log.setup(debug_mode = True)


def test_zero_exit_status():
    """Tests zero exit status."""

    assert psh.true().status() == 0


def test_nonzero_exit_status():
    """Tests nonzero exit status."""

    assert pytest.raises(psh.ExecutionError,
        lambda: psh.false()).value.status == 1


def test_ok_statuses():
    """Tests _ok_statuses option."""

    assert psh.false(_ok_statuses = [ 0, 1 ] ).status() == 1
    assert pytest.raises(psh.ExecutionError,
        lambda: psh.true(_ok_statuses = [])).value.status == 0
